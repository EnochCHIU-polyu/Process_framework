"""
POST /process/run/{session_id}  — run the PROCESS framework pipeline on stored chat messages.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from process_framework import (
    AuditType,
    BadCaseCategory,
    EvaluationCase,
    ProcessFramework,
    ScenarioType,
)
from process_framework.api.config import Settings, get_settings

router = APIRouter()


class ProcessRunResponse(BaseModel):
    session_id: str
    report_id: str
    overall_risk_level: Optional[str]
    total_cases: int


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------


def _supa_headers(settings: Settings) -> Dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def _fetch_messages(
    client: httpx.AsyncClient,
    settings: Settings,
    session_id: str,
) -> List[Dict[str, Any]]:
    url = (
        f"{settings.supabase_url}/rest/v1/chat_messages"
        f"?session_id=eq.{session_id}&order=created_at.asc"
        f"&select=id,role,content,created_at"
    )
    resp = await client.get(url, headers=_supa_headers(settings))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Supabase error: {resp.text}")
    return resp.json()


async def _fetch_bad_cases(
    client: httpx.AsyncClient,
    settings: Settings,
    session_id: str,
) -> List[Dict[str, Any]]:
    url = (
        f"{settings.supabase_url}/rest/v1/bad_cases"
        f"?session_id=eq.{session_id}&select=message_id,category,reason,ignored_keywords"
    )
    resp = await client.get(url, headers=_supa_headers(settings))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Supabase error: {resp.text}")
    return resp.json()


async def _persist_report(
    client: httpx.AsyncClient,
    settings: Settings,
    report_id: str,
    session_id: str,
    report: Dict[str, Any],
) -> None:
    url = f"{settings.supabase_url}/rest/v1/process_reports"
    payload = {
        "id": report_id,
        "session_id": session_id,
        "report": report,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post(url, json=payload, headers=_supa_headers(settings))
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Supabase persist report failed: {resp.text}",
        )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/process/run/{session_id}", response_model=ProcessRunResponse)
async def run_process(
    session_id: str,
    settings: Settings = Depends(get_settings),
) -> Any:
    """
    Build an EvaluationCase list from stored chat_messages for the given session,
    run the full PROCESS framework pipeline, and persist the report JSON.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        messages = await _fetch_messages(client, settings, session_id)
        if not messages:
            raise HTTPException(
                status_code=404,
                detail=f"No messages found for session {session_id!r}.",
            )
        bad_cases_data = await _fetch_bad_cases(client, settings, session_id)

    # Build a lookup of bad-case data keyed by message_id
    bad_case_map: Dict[str, Dict[str, Any]] = {
        bc["message_id"]: bc for bc in bad_cases_data
    }

    # Pair user / assistant turns into EvaluationCases, tracking assistant message IDs
    evaluation_cases: List[EvaluationCase] = []
    assistant_msg_ids: List[str] = []
    user_buf: Optional[str] = None

    for msg in messages:
        if msg["role"] == "user":
            user_buf = msg["content"]
        elif msg["role"] == "assistant" and user_buf is not None:
            evaluation_cases.append(
                EvaluationCase(
                    scenario_type=ScenarioType.QA,
                    user_input=user_buf,
                    expected_output="",  # not available from stored data
                    actual_output=msg["content"],
                )
            )
            assistant_msg_ids.append(msg["id"])
            user_buf = None

    # Run PROCESS framework pipeline
    framework = ProcessFramework(audit_type=AuditType.NEW_PRODUCT)
    framework.setup_purpose(
        description=f"Chat session audit — session {session_id}",
        total_sample_size=max(len(evaluation_cases), 1),
    )
    framework.add_evaluation_cases(evaluation_cases)
    framework.build_dataset_report()

    # Register known bad cases using the pre-built lookup map
    for case, asst_id in zip(evaluation_cases, assistant_msg_ids):
        bc = bad_case_map.get(asst_id)
        if bc and bc.get("reason"):
            try:
                category = BadCaseCategory(bc.get("category", "hallucination"))
            except ValueError:
                category = BadCaseCategory.HALLUCINATION
            framework.record_bad_case(
                evaluation_case=case,
                category=category,
                description=bc["reason"],
                ignored_keywords=bc.get("ignored_keywords") or [],
            )

    framework.build_bad_case_report(total_evaluated=len(evaluation_cases))
    framework.plan_evaluation_count()
    framework.build_effectiveness_report()

    full_report = framework.generate_full_report()
    report_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=30.0) as client:
        await _persist_report(client, settings, report_id, session_id, full_report)

    return ProcessRunResponse(
        session_id=session_id,
        report_id=report_id,
        overall_risk_level=full_report.get("overall_risk_level"),
        total_cases=len(evaluation_cases),
    )
