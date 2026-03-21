"""
自動審計系統 — 自動分析聊天對話，識別幻覺和壞案例，積累微調數據。

核心循環：
1. 從 Supabase 提取未審計的聊天對話對 (user_input, assistant_output)
2. 用 LLM-as-a-Judge 評分（幻覺、事實性等）
3. 自動標記低分案例為「潛在幻覺」
4. 與已知壞案例對比，檢測相似性
5. 生成微調數據集和改進建議
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from process_framework import (
    AuditType,
    BadCaseCategory,
    EvaluationCase,
    EvaluationDimension,
    EvaluationScore,
    ProcessFramework,
    ScenarioType,
    ScoreLevel,
)
from process_framework.api.config import Settings
from process_framework.api.feedback import build_session_guard
from process_framework.api.llm_judge import llm_judge_evaluate

logger = logging.getLogger(__name__)


_DISSATISFACTION_KEYWORDS = (
    "not true",
    "wrong",
    "incorrect",
    "hallucination",
    "false",
    "answer again",
    "reanswer",
    "too long",
    "not good",
    "please answer again",
)

_DISSATISFACTION_PATTERNS = (
    re.compile(r"^\s*no\b", re.IGNORECASE),
    re.compile(r"\bthis is not true\b", re.IGNORECASE),
    re.compile(r"\bit is not true\b", re.IGNORECASE),
)


def _has_user_dissatisfaction_signal(user_input: str) -> bool:
    normalized = (user_input or "").strip().lower()
    if not normalized:
        return False
    if any(keyword in normalized for keyword in _DISSATISFACTION_KEYWORDS):
        return True
    return any(pattern.search(user_input or "") for pattern in _DISSATISFACTION_PATTERNS)


class AutoAuditResult(BaseModel):
    """自動審計結果"""
    audit_id: str
    session_id: str
    total_pairs_analyzed: int
    hallucinations_detected: int
    low_quality_cases: int
    potential_bad_cases: List[Dict[str, Any]]
    finetuning_dataset: List[Dict[str, Any]]
    overall_risk_score: float  # 0.0-1.0, 1.0 = 最高風險
    improvement_suggestions: List[str]
    created_at: str


class ChatIOPair(BaseModel):
    """聊天輸入輸出對"""
    message_id: str
    session_id: str
    user_input: str
    assistant_output: str
    created_at: str
    is_already_marked_bad: bool = False
    existing_bad_case_reason: Optional[str] = None


def _infer_bad_case_category(case: Dict[str, Any]) -> str:
    hall_level = int(case.get("hallucination_level", 3) or 3)
    factual = int(case.get("factual_grounding", 3) or 3)
    if hall_level <= 2 or factual <= 2:
        return "hallucination"
    return "user_experience"


async def _supa_headers(settings: Settings) -> Dict[str, str]:
    """Supabase API 請求頭"""
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


async def _fetch_unaudited_pairs(
    client: httpx.AsyncClient,
    settings: Settings,
    session_id: Optional[str] = None,
) -> List[ChatIOPair]:
    """從 pending ai_audits 提取同 session 的 assistant/user 配對。"""

    headers = await _supa_headers(settings)

    if session_id:
        audit_filter = f"?status=eq.pending&session_id=eq.{session_id}&select=id,message_id,session_id,created_at&order=created_at.asc"
    else:
        audit_filter = "?status=eq.pending&select=id,message_id,session_id,created_at&order=created_at.asc"

    audits_url = f"{settings.supabase_url}/rest/v1/ai_audits{audit_filter}"
    audits_resp = await client.get(audits_url, headers=headers)
    if audits_resp.status_code != 200:
        return []

    pending_audits = audits_resp.json()
    if not pending_audits:
        return []

    sessions = sorted({str(a["session_id"]) for a in pending_audits if a.get("session_id")})
    pairs: List[ChatIOPair] = []

    for sid in sessions:
        msg_url = (
            f"{settings.supabase_url}/rest/v1/chat_messages"
            f"?session_id=eq.{sid}&select=id,session_id,role,content,created_at&order=created_at.asc"
        )
        msg_resp = await client.get(msg_url, headers=headers)
        if msg_resp.status_code != 200:
            continue

        messages = msg_resp.json()
        if not isinstance(messages, list) or not messages:
            continue

        index_by_id = {m["id"]: i for i, m in enumerate(messages) if m.get("id")}

        pending_for_session = [a for a in pending_audits if str(a.get("session_id")) == sid]
        for audit in pending_for_session:
            message_id = audit.get("message_id")
            if not message_id or message_id not in index_by_id:
                continue

            assistant_idx = index_by_id[message_id]
            assistant_msg = messages[assistant_idx]
            if assistant_msg.get("role") != "assistant":
                continue

            user_input = ""
            for idx in range(assistant_idx - 1, -1, -1):
                if messages[idx].get("role") == "user":
                    user_input = str(messages[idx].get("content") or "")
                    break

            bad_case_url = (
                f"{settings.supabase_url}/rest/v1/bad_cases"
                f"?message_id=eq.{assistant_msg['id']}&select=reason,category"
            )
            bad_case_resp = await client.get(bad_case_url, headers=headers)
            is_marked = False
            reason = None
            if bad_case_resp.status_code == 200:
                bad_cases = bad_case_resp.json()
                if bad_cases:
                    is_marked = True
                    reason = bad_cases[0].get("reason")

            pairs.append(
                ChatIOPair(
                    message_id=str(assistant_msg["id"]),
                    session_id=str(assistant_msg["session_id"]),
                    user_input=user_input,
                    assistant_output=str(assistant_msg.get("content") or ""),
                    created_at=str(assistant_msg.get("created_at") or ""),
                    is_already_marked_bad=is_marked,
                    existing_bad_case_reason=reason,
                )
            )

    pairs.sort(key=lambda p: p.created_at)
    return pairs


async def _fetch_recent_session_pairs(
    client: httpx.AsyncClient,
    settings: Settings,
    session_id: str,
    limit_pairs: int = 5,
) -> List[ChatIOPair]:
    """
    Fallback: fetch most recent assistant/user pairs from one session.

    Used when there are no pending ai_audits, so manual or repeated auto-audit
    still returns useful content instead of an empty report.
    """
    headers = await _supa_headers(settings)
    msg_url = (
        f"{settings.supabase_url}/rest/v1/chat_messages"
        f"?session_id=eq.{session_id}&select=id,session_id,role,content,created_at&order=created_at.asc"
    )
    resp = await client.get(msg_url, headers=headers)
    if resp.status_code != 200:
        return []

    messages = resp.json()
    if not isinstance(messages, list) or not messages:
        return []

    pairs: List[ChatIOPair] = []
    for idx, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue

        user_input = ""
        for j in range(idx - 1, -1, -1):
            if messages[j].get("role") == "user":
                user_input = str(messages[j].get("content") or "")
                break

        if not user_input:
            continue

        pairs.append(
            ChatIOPair(
                message_id=str(msg.get("id") or ""),
                session_id=str(msg.get("session_id") or session_id),
                user_input=user_input,
                assistant_output=str(msg.get("content") or ""),
                created_at=str(msg.get("created_at") or ""),
                is_already_marked_bad=False,
                existing_bad_case_reason=None,
            )
        )

    if not pairs:
        return []

    pairs.sort(key=lambda p: p.created_at)
    return pairs[-limit_pairs:]


async def _detect_hallucinations(
    pairs: List[ChatIOPair],
    settings: Settings,
) -> Dict[str, Any]:
    """用 LLM Judge 檢測幻覺和低品質案例"""
    
    hallucinations = []
    low_quality = []
    scores_map = {}  # message_id → scores
    risk_scores = []
    heuristic_bad_case_ids: set[str] = set()

    # Heuristic: if user turn is explicit disagreement, previous assistant turn is likely problematic.
    for idx, pair in enumerate(pairs):
        if not _has_user_dissatisfaction_signal(pair.user_input):
            continue
        if idx == 0:
            continue
        prev_pair = pairs[idx - 1]
        if prev_pair.is_already_marked_bad:
            continue
        if prev_pair.message_id in heuristic_bad_case_ids:
            continue

        heuristic_bad_case_ids.add(prev_pair.message_id)
        heuristic_case = {
            "message_id": prev_pair.message_id,
            "session_id": prev_pair.session_id,
            "user_input": prev_pair.user_input,
            "output": prev_pair.assistant_output,
            "hallucination_level": 2,
            "factual_grounding": 2,
            "reasoning_quality": 2,
            "risk_score": 0.75,
            "source": "user_feedback_signal",
            "trigger_feedback": pair.user_input,
        }
        hallucinations.append(heuristic_case)
        low_quality.append(
            {
                "message_id": prev_pair.message_id,
                "session_id": prev_pair.session_id,
                "user_input": prev_pair.user_input,
                "output": prev_pair.assistant_output,
                "average_score": 2.0,
                "scores": {
                    "factual_grounding": 2,
                    "semantic_correctness": 2,
                    "reasoning_quality": 2,
                    "hallucination_level": 2,
                    "answer_accuracy": 2,
                },
                "risk_score": 0.75,
                "source": "user_feedback_signal",
            }
        )
        risk_scores.append(0.75)
    
    for pair in pairs:
        # 已標記為壞案例的跳過自動檢測
        if pair.is_already_marked_bad:
            scores_map[pair.message_id] = {
                "status": "already_marked",
                "reason": pair.existing_bad_case_reason,
            }
            continue

        # Feedback turns are not QA prompts; skip score judging here.
        if _has_user_dissatisfaction_signal(pair.user_input):
            scores_map[pair.message_id] = {
                "status": "feedback_turn",
                "reason": "User dissatisfaction feedback turn; excluded from positive QA scoring.",
            }
            continue
        
        # 用 LLM Judge 評分
        scores = await llm_judge_evaluate(
            user_input=pair.user_input,
            actual_output=pair.assistant_output,
            settings=settings,
            temperature=0.0,
        )
        
        if not scores:
            continue
        
        scores_map[pair.message_id] = scores
        
        # 計算風險分數（反轉標準化）
        hallucination_level = scores.get("hallucination_level", 3)
        factual_grounding = scores.get("factual_grounding", 3)
        reasoning_quality = scores.get("reasoning_quality", 3)
        
        # 風險分數 = (5 - 平均分) / 4
        raw_avg = (hallucination_level + factual_grounding + reasoning_quality) / 3
        risk_score = (5 - raw_avg) / 4
        risk_scores.append(risk_score)
        
        # 識別幻覺 (hallucination_level < 3)
        if hallucination_level <= 2:
            hallucinations.append({
                "message_id": pair.message_id,
                "session_id": pair.session_id,
                "user_input": pair.user_input,
                "output": pair.assistant_output,
                "hallucination_level": hallucination_level,
                "factual_grounding": factual_grounding,
                "reasoning_quality": reasoning_quality,
                "risk_score": risk_score,
            })
        
        # 識別低品質案例 (平均分 < 3)
        if raw_avg < 3:
            low_quality.append({
                "message_id": pair.message_id,
                "session_id": pair.session_id,
                "user_input": pair.user_input,
                "output": pair.assistant_output,
                "average_score": raw_avg,
                "scores": scores,
                "risk_score": risk_score,
            })
    
    overall_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
    
    return {
        "hallucinations": hallucinations,
        "low_quality_cases": low_quality,
        "scores_map": scores_map,
        "overall_risk_score": min(1.0, overall_risk),  # Cap at 1.0
    }


async def _generate_finetuning_dataset(
    pairs: List[ChatIOPair],
    hallucinations: List[Dict[str, Any]],
    low_quality: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """生成微調數據集"""
    
    finetuning_data = []
    
    # 1. 低品質案例 → 用於負樣本訓練
    for case in low_quality:
        finetuning_data.append({
            "type": "negative_example",
            "user_input": case["user_input"],
            "poor_output": case["output"],
            "issue": "low_quality",
            "average_score": case["average_score"],
            "learning_target": "避免此類回應品質",
        })
    
    # 2. 幻覺案例 → 用於對抗性訓練
    for case in hallucinations:
        finetuning_data.append({
            "type": "hallucination_example",
            "user_input": case["user_input"],
            "hallucinated_output": case["output"],
            "hallucination_level": case["hallucination_level"],
            "learning_target": "檢測並避免事實不符的回應",
        })
    
    # 3. 只保留壞案例導向資料，避免報告過大與學習噪音
    return finetuning_data


def _generate_improvement_suggestions(
    hallucinations: List[Dict[str, Any]],
    low_quality: List[Dict[str, Any]],
    pairs: List[ChatIOPair],
) -> List[str]:
    """基於檢測結果生成改進建議"""
    
    suggestions = []
    
    if not hallucinations and not low_quality:
        suggestions.append("✅ 未檢測到顯著的幻覺或低品質案例")
        return suggestions
    
    # 統計分析
    if hallucinations:
        pct = len(hallucinations) / len(pairs) * 100 if pairs else 0
        suggestions.append(
            f"⚠️ 檢測到 {len(hallucinations)} 個幻覺案例 ({pct:.1f}%)，"
            f"建議優先進行對抗性訓練或加入事實核查機制"
        )
    
    if low_quality:
        pct = len(low_quality) / len(pairs) * 100 if pairs else 0
        suggestions.append(
            f"📊 {len(low_quality)} 個低品質案例 ({pct:.1f}%)，"
            f"建議審查訓練數據或調整模型超參數"
        )
    
    # 具體建議
    if len(hallucinations) > len(pairs) * 0.1:
        suggestions.append(
            "🔧 幻覺比例過高（>10%），建議："
            "1) 增加領域知識基礎；"
            "2) 啟用檢索增強生成 (RAG)；"
            "3) 加強事實驗證層"
        )
    
    suggestions.append(
        "📈 建議下一步："
        "1) 將檢測到的案例導入微調數據集；"
        "2) 執行有監督微調；"
        "3) A/B 測試新模型版本"
    )
    
    return suggestions


async def run_auto_audit(
    settings: Settings,
    session_id: Optional[str] = None,
) -> AutoAuditResult:
    """執行自動審計及完整循環"""
    
    audit_id = str(uuid.uuid4())
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1️⃣ 提取聊天對話對
        pairs = await _fetch_unaudited_pairs(client, settings, session_id)

        # Fallback for repeated/manual runs: no pending audits but session exists.
        if not pairs and session_id:
            pairs = await _fetch_recent_session_pairs(
                client,
                settings,
                session_id=session_id,
                limit_pairs=5,
            )
        
        if not pairs:
            return AutoAuditResult(
                audit_id=audit_id,
                session_id=session_id or "all",
                total_pairs_analyzed=0,
                hallucinations_detected=0,
                low_quality_cases=0,
                potential_bad_cases=[],
                finetuning_dataset=[],
                overall_risk_score=0.0,
                improvement_suggestions=["無待審計的聊天對話，且找不到可回溯的最近會話配對。"],
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        
        # 2️⃣ 檢測幻覺和低品質
        detection_result = await _detect_hallucinations(pairs, settings)
        
        hallucinations = detection_result["hallucinations"]
        low_quality_cases = detection_result["low_quality_cases"]
        
        # 3️⃣ 生成微調數據集
        finetuning_data = await _generate_finetuning_dataset(
            pairs, hallucinations, low_quality_cases
        )
        
        # 4️⃣ 生成改進建議
        suggestions = _generate_improvement_suggestions(
            hallucinations, low_quality_cases, pairs
        )

        # 4.5️⃣ 將自動審計判斷回寫到 ai_audits（便於在表格中直接查看）
        await _write_ai_audit_triage(client, settings, pairs, detection_result)
    
    # 5️⃣ 構建結果
    return AutoAuditResult(
        audit_id=audit_id,
        session_id=session_id or "all",
        total_pairs_analyzed=len(pairs),
        hallucinations_detected=len(hallucinations),
        low_quality_cases=len(low_quality_cases),
        potential_bad_cases=hallucinations + low_quality_cases,
        finetuning_dataset=finetuning_data,
        overall_risk_score=detection_result["overall_risk_score"],
        improvement_suggestions=suggestions,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def _write_ai_audit_triage(
    client: httpx.AsyncClient,
    settings: Settings,
    pairs: List[ChatIOPair],
    detection_result: Dict[str, Any],
) -> None:
    """回寫 ai_audits triage 欄位，讓自動審計結果可在 ai_audits 直接追蹤。"""

    hallucination_ids = {
        str(item.get("message_id"))
        for item in detection_result.get("hallucinations", [])
        if item.get("message_id")
    }
    low_quality_ids = {
        str(item.get("message_id"))
        for item in detection_result.get("low_quality_cases", [])
        if item.get("message_id")
    }
    flagged_ids = hallucination_ids.union(low_quality_ids)
    scores_map: Dict[str, Any] = detection_result.get("scores_map", {}) or {}

    headers = await _supa_headers(settings)

    for pair in pairs:
        if pair.is_already_marked_bad:
            continue

        message_id = pair.message_id
        audit_url = (
            f"{settings.supabase_url}/rest/v1/ai_audits"
            f"?message_id=eq.{message_id}&session_id=eq.{pair.session_id}"
        )

        if message_id in flagged_ids:
            status = "suspected_hallucination"
            verdict = "bad_case"
            label = "bad_case"
            summary = "Auto-audit detected risk from scoring/feedback signals."
        else:
            status = "reviewed"
            verdict = "ok"
            score_info = scores_map.get(message_id, {})
            if isinstance(score_info, dict) and score_info.get("status") == "feedback_turn":
                label = "preference"
                summary = str(score_info.get("reason") or "Feedback-style turn; reviewed as preference/formatting signal.")
            else:
                label = "quality_ok"
                summary = "Auto-audit reviewed; no significant hallucination/low-quality risk detected."

        payload = {
            "status": status,
            "verdict": verdict,
            "analysis_label": label,
            "analysis_summary": summary,
            "triaged_at": datetime.now(timezone.utc).isoformat(),
            "report_context": {
                "source": "auto_audit",
                "user_input": pair.user_input,
                "assistant_output": pair.assistant_output,
            },
        }

        try:
            resp = await client.patch(audit_url, json=payload, headers=headers)
            if resp.status_code not in (200, 204):
                logger.warning("Auto-audit triage write failed for message %s: %s", message_id, resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Auto-audit triage exception for message %s: %s", message_id, exc)


async def persist_auto_audit_report(
    client: httpx.AsyncClient,
    settings: Settings,
    result: AutoAuditResult,
) -> None:
    """將自動審計報告存到 Supabase"""
    
    url = f"{settings.supabase_url}/rest/v1/auto_audit_reports"
    payload = {
        "id": result.audit_id,
        "session_id": result.session_id,
        "report": result.dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }
    
    await client.post(url, json=payload, headers=headers)


async def promote_bad_cases_from_report(
    client: httpx.AsyncClient,
    settings: Settings,
    result: AutoAuditResult,
) -> int:
    """
    Persist first-time bad cases from auto-audit report into bad_cases table.

    - De-duplicates by message_id (skip if bad_cases already exists)
    - Updates ai_audits with bad_case_id linkage
    - Refreshes learned patterns for affected sessions

    Returns number of newly inserted bad_cases rows.
    """
    headers = await _supa_headers(settings)
    inserted = 0
    seen_message_ids: set[str] = set()
    affected_sessions: set[str] = set()

    for case in result.potential_bad_cases:
        message_id = str(case.get("message_id") or "").strip()
        session_id = str(case.get("session_id") or result.session_id or "").strip()
        if not message_id or not session_id:
            continue
        if message_id in seen_message_ids:
            continue
        seen_message_ids.add(message_id)

        # Skip if already exists in bad_cases
        exists_url = (
            f"{settings.supabase_url}/rest/v1/bad_cases"
            f"?message_id=eq.{message_id}&select=id&limit=1"
        )
        exists_resp = await client.get(exists_url, headers=headers)
        if exists_resp.status_code == 200 and (exists_resp.json() or []):
            existing_id = str(exists_resp.json()[0].get("id"))
            link_url = (
                f"{settings.supabase_url}/rest/v1/ai_audits"
                f"?message_id=eq.{message_id}&session_id=eq.{session_id}"
            )
            await client.patch(
                link_url,
                json={
                    "status": "suspected_hallucination",
                    "verdict": "bad_case",
                    "bad_case_id": existing_id,
                },
                headers=headers,
            )
            affected_sessions.add(session_id)
            continue

        bad_case_id = str(uuid.uuid4())
        category = _infer_bad_case_category(case)
        reason = "Auto-audit detected high-risk response from user-feedback/LLM scoring."
        if case.get("source") == "user_feedback_signal":
            reason = "Auto-audit detected user dissatisfaction signal for this answer."

        payload = {
            "id": bad_case_id,
            "message_id": message_id,
            "session_id": session_id,
            "reason": reason,
            "category": category,
            "notes": f"AutoAudit: {case.get('trigger_feedback') or ''}".strip(),
            "expected_output": None,
            "actual_output": case.get("output"),
            "ignored_keywords": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        insert_url = f"{settings.supabase_url}/rest/v1/bad_cases"
        insert_resp = await client.post(insert_url, json=payload, headers=headers)
        if insert_resp.status_code not in (200, 201):
            logger.warning("Auto-audit bad_case insert failed for message %s: %s", message_id, insert_resp.text)
            continue

        # Link ai_audits to new bad_case
        link_url = (
            f"{settings.supabase_url}/rest/v1/ai_audits"
            f"?message_id=eq.{message_id}&session_id=eq.{session_id}"
        )
        await client.patch(
            link_url,
            json={
                "status": "suspected_hallucination",
                "verdict": "bad_case",
                "bad_case_id": bad_case_id,
            },
            headers=headers,
        )

        inserted += 1
        affected_sessions.add(session_id)

    # Refresh learned patterns so next responses can avoid repeated mistakes
    for sid in affected_sessions:
        try:
            await build_session_guard(sid, settings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed refreshing learned patterns for session %s: %s", sid, exc)

    return inserted
