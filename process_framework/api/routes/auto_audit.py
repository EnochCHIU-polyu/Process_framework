"""
自動審計 API 路由 — 觸發和查詢自動審計結果

核心端點：
- POST /auto-audit/run — 觸發自動審計循環
- GET /auto-audit/report/{audit_id} — 查詢審計報告
"""

from __future__ import annotations

from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from process_framework.api.auto_audit import (
    AutoAuditResult,
    persist_auto_audit_report,
    run_auto_audit,
)
from process_framework.api.config import Settings, get_settings

router = APIRouter()


class AutoAuditRequest(BaseModel):
    """自動審計請求"""
    session_id: Optional[str] = None  # 若為 None，分析所有會話


class AutoAuditResponse(BaseModel):
    """自動審計回應"""
    audit_id: str
    session_id: str
    status: str = "completed"
    total_pairs_analyzed: int
    hallucinations_detected: int
    low_quality_cases: int
    overall_risk_score: float
    improvement_suggestions: list


@router.post("/auto-audit/run", response_model=AutoAuditResponse)
async def run_auto_audit_endpoint(
    req: AutoAuditRequest,
    settings: Settings = Depends(get_settings),
) -> Any:
    """
    觸發自動審計循環：
    1. 提取聊天對話對 (user input, assistant output)
    2. 用 LLM Judge 檢測幻覺
    3. 識別低品質案例
    4. 生成微調數據集
    5. 生成改進建議

    Args:
        req.session_id: 指定會話 ID（可選）；若不指定則分析所有會話

    Returns:
        包含審計結果、風險分數和改進建議的報告
    """
    result = await run_auto_audit(settings, session_id=req.session_id)

    # 持久化報告到 Supabase
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            await persist_auto_audit_report(client, settings, result)
        except Exception as e:
            pass  # 記錄失敗但不中斷審計

    return AutoAuditResponse(
        audit_id=result.audit_id,
        session_id=result.session_id,
        total_pairs_analyzed=result.total_pairs_analyzed,
        hallucinations_detected=result.hallucinations_detected,
        low_quality_cases=result.low_quality_cases,
        overall_risk_score=result.overall_risk_score,
        improvement_suggestions=result.improvement_suggestions,
    )


@router.get("/auto-audit/report/{audit_id}")
async def get_auto_audit_report(
    audit_id: str,
    settings: Settings = Depends(get_settings),
) -> Any:
    """
    查詢自動審計報告

    Args:
        audit_id: 審計 ID

    Returns:
        完整的審計報告（含幻覺案例、微調數據集等）
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }
        url = (
            f"{settings.supabase_url}/rest/v1/auto_audit_reports"
            f"?id=eq.{audit_id}&select=report"
        )
        resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Supabase query failed")

        rows = resp.json()
        if not rows:
            raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

        return rows[0]["report"]


@router.get("/auto-audit/latest")
async def get_latest_auto_audit(
    session_id: Optional[str] = None,
    settings: Settings = Depends(get_settings),
) -> Any:
    """
    查詢最新的自動審計報告

    Args:
        session_id: 指定會話 ID（可選）

    Returns:
        最新審計報告
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }

        if session_id:
            filter_str = f"?session_id=eq.{session_id}"
        else:
            filter_str = ""

        url = (
            f"{settings.supabase_url}/rest/v1/auto_audit_reports"
            f"{filter_str}&order=created_at.desc&limit=1&select=report"
        )
        resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Supabase query failed")

        rows = resp.json()
        if not rows:
            raise HTTPException(status_code=404, detail="No audit reports found")

        return rows[0]["report"]
