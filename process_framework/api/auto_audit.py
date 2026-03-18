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
from process_framework.api.llm_judge import llm_judge_evaluate


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
    """從資料庫提取未審計的聊天對話對"""
    
    # 先獲取所有訊息
    if session_id:
        filter_str = f"?session_id=eq.{session_id}&order=created_at.asc&select=id,session_id,role,content,created_at"
    else:
        filter_str = "?order=created_at.asc&select=id,session_id,role,content,created_at"
    
    url = f"{settings.supabase_url}/rest/v1/chat_messages{filter_str}"
    resp = await client.get(url, headers=await _supa_headers(settings))
    if resp.status_code != 200:
        return []
    
    messages = resp.json()
    
    # 配對 user 和 assistant 訊息
    pairs: List[ChatIOPair] = []
    current_session = None
    user_buf = None
    
    for msg in messages:
        if msg["role"] == "user":
            user_buf = msg
        elif msg["role"] == "assistant" and user_buf:
            current_session = msg["session_id"]
            
            # 查詢該助手訊息是否已標記為壞案例
            bad_case_url = (
                f"{settings.supabase_url}/rest/v1/bad_cases"
                f"?message_id=eq.{msg['id']}&select=reason,category"
            )
            bad_case_resp = await client.get(bad_case_url, headers=await _supa_headers(settings))
            is_marked = False
            reason = None
            if bad_case_resp.status_code == 200:
                bad_cases = bad_case_resp.json()
                if bad_cases:
                    is_marked = True
                    reason = bad_cases[0].get("reason")
            
            pairs.append(
                ChatIOPair(
                    message_id=msg["id"],
                    session_id=msg["session_id"],
                    user_input=user_buf["content"],
                    assistant_output=msg["content"],
                    created_at=msg["created_at"],
                    is_already_marked_bad=is_marked,
                    existing_bad_case_reason=reason,
                )
            )
            user_buf = None
    
    return pairs


async def _detect_hallucinations(
    pairs: List[ChatIOPair],
    settings: Settings,
) -> Dict[str, Any]:
    """用 LLM Judge 檢測幻覺和低品質案例"""
    
    hallucinations = []
    low_quality = []
    scores_map = {}  # message_id → scores
    risk_scores = []
    
    for pair in pairs:
        # 已標記為壞案例的跳過自動檢測
        if pair.is_already_marked_bad:
            scores_map[pair.message_id] = {
                "status": "already_marked",
                "reason": pair.existing_bad_case_reason,
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
    
    # 3. 高品質案例（作為正樣本）
    for pair in pairs[:10]:  # 取前 10 個作為示例
        if pair.message_id not in [h["message_id"] for h in hallucinations] \
           and pair.message_id not in [l["message_id"] for l in low_quality]:
            finetuning_data.append({
                "type": "positive_example",
                "user_input": pair.user_input,
                "good_output": pair.assistant_output,
                "learning_target": "保持或提升此類回應品質",
            })
    
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
                improvement_suggestions=["無待審計的聊天對話"],
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
