"""
POST /audit/{message_id}/mark-bad  — mark an assistant response as a bad case.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from process_framework.api.config import Settings, get_settings

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class MarkBadRequest(BaseModel):
    reason: str
    category: str = "hallucination"  # matches BadCaseCategory values
    notes: Optional[str] = None
    reviewer: Optional[str] = None
    root_cause: Optional[str] = None
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    ignored_keywords: Optional[List[str]] = None


class MarkBadResponse(BaseModel):
    bad_case_id: str
    audit_id: str
    message_id: str
    status: str = "bad_case"


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


async def _fetch_message(
    client: httpx.AsyncClient,
    settings: Settings,
    message_id: str,
) -> Dict[str, Any]:
    """Fetch a chat_messages row; raise 404 if not found."""
    url = (
        f"{settings.supabase_url}/rest/v1/chat_messages"
        f"?id=eq.{message_id}&select=id,session_id,role,content"
    )
    resp = await client.get(url, headers=_supa_headers(settings))
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Supabase error: {resp.text}")
    rows = resp.json()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Message {message_id!r} not found.")
    return rows[0]


async def _insert_bad_case(
    client: httpx.AsyncClient,
    settings: Settings,
    bad_case_id: str,
    message_id: str,
    session_id: str,
    req: MarkBadRequest,
) -> None:
    url = f"{settings.supabase_url}/rest/v1/bad_cases"
    payload = {
        "id": bad_case_id,
        "message_id": message_id,
        "session_id": session_id,
        "reason": req.reason,
        "category": req.category,
        "notes": req.notes,
        "reviewer": req.reviewer,
        "root_cause": req.root_cause,
        "expected_output": req.expected_output,
        "actual_output": req.actual_output,
        "ignored_keywords": req.ignored_keywords or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post(url, json=payload, headers=_supa_headers(settings))
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Supabase insert bad_case failed: {resp.text}",
        )


async def _insert_audit_verdict(
    client: httpx.AsyncClient,
    settings: Settings,
    audit_id: str,
    message_id: str,
    session_id: str,
    bad_case_id: str,
) -> None:
    url = f"{settings.supabase_url}/rest/v1/ai_audits"
    payload = {
        "id": audit_id,
        "message_id": message_id,
        "session_id": session_id,
        "status": "suspected_hallucination",
        "verdict": "bad_case",
        "bad_case_id": bad_case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post(url, json=payload, headers=_supa_headers(settings))
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Supabase insert audit verdict failed: {resp.text}",
        )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/audit/{message_id}/mark-bad", response_model=MarkBadResponse)
async def mark_bad(
    message_id: str,
    req: MarkBadRequest,
    settings: Settings = Depends(get_settings),
) -> Any:
    """
    Mark an assistant response as a bad case (e.g. hallucination).

    - Inserts a row into ``bad_cases`` with detailed attribution.
    - Inserts a new ``ai_audits`` row with ``verdict=bad_case``.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        msg = await _fetch_message(client, settings, message_id)
        session_id: str = msg["session_id"]

        bad_case_id = str(uuid.uuid4())
        audit_id = str(uuid.uuid4())

        await _insert_bad_case(client, settings, bad_case_id, message_id, session_id, req)
        await _insert_audit_verdict(
            client, settings, audit_id, message_id, session_id, bad_case_id
        )

    return MarkBadResponse(
        bad_case_id=bad_case_id,
        audit_id=audit_id,
        message_id=message_id,
        status="bad_case",
    )
