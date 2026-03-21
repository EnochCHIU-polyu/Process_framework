from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from process_framework.api.config import Settings

logger = logging.getLogger(__name__)


def _headers(settings: Settings) -> Dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def map_error_type_to_category(error_type: str) -> str:
    normalized = (error_type or "").strip().lower()
    mapping = {
        "hallucination": "hallucination",
        "factual_error": "factual",
        "intent_misunderstanding": "intent_understanding",
        "constraint_ignored": "user_experience",
        "tone_issue": "user_experience",
        "other": "user_experience",
    }
    return mapping.get(normalized, "user_experience")


async def save_user_correction(
    session_id: str,
    corrected_message_id: str,
    user_question: str,
    assistant_answer: str,
    user_feedback: str,
    correction_data: Dict[str, Any],
    settings: Settings,
) -> Optional[str]:
    payload = {
        "id": str(uuid.uuid4()),
        "message_id": corrected_message_id,
        "session_id": session_id,
        "reason": correction_data.get("reason") or "User provided correction feedback.",
        "category": map_error_type_to_category(str(correction_data.get("error_type", "other"))),
        "notes": f"User feedback: {user_feedback}\nQuestion: {user_question}",
        "expected_output": correction_data.get("correct_answer"),
        "actual_output": assistant_answer,
        "ignored_keywords": correction_data.get("ignored_keywords") or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    url = f"{settings.supabase_url}/rest/v1/bad_cases"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=_headers(settings))
        if resp.status_code not in (200, 201, 204):
            logger.warning("Failed saving correction to bad_cases: %s", resp.text)
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Exception saving correction to bad_cases: %s", exc)
        return None

    return str(payload["id"])


async def mark_audit_as_bad_case(
    session_id: str,
    corrected_message_id: str,
    bad_case_id: str,
    settings: Settings,
) -> bool:
    url = (
        f"{settings.supabase_url}/rest/v1/ai_audits"
        f"?session_id=eq.{session_id}&message_id=eq.{corrected_message_id}"
    )
    payload = {
        "status": "suspected_hallucination",
        "verdict": "bad_case",
        "bad_case_id": bad_case_id,
    }
    headers = {
        **_headers(settings),
        "Prefer": "return=minimal",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.patch(url, json=payload, headers=headers)
        if resp.status_code not in (200, 204):
            logger.warning("Failed updating ai_audits as bad_case: %s", resp.text)
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Exception updating ai_audits as bad_case: %s", exc)
        return False

    return True


async def attach_feedback_context_to_audit(
    session_id: str,
    corrected_message_id: str,
    user_question: str,
    assistant_answer: str,
    user_feedback: str,
    settings: Settings,
) -> bool:
    url = (
        f"{settings.supabase_url}/rest/v1/ai_audits"
        f"?session_id=eq.{session_id}&message_id=eq.{corrected_message_id}"
    )
    payload = {
        "status": "pending",
        "report_context": {
            "user_question": user_question,
            "assistant_answer": assistant_answer,
            "user_feedback": user_feedback,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.patch(url, json=payload, headers=_headers(settings))
        if resp.status_code not in (200, 204):
            logger.warning("Failed attaching feedback context to ai_audits: %s", resp.text)
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Exception attaching feedback context to ai_audits: %s", exc)
        return False

    return True


async def finalize_audit_triage(
    session_id: str,
    corrected_message_id: str,
    classification: str,
    summary: str,
    settings: Settings,
    bad_case_id: Optional[str] = None,
) -> bool:
    normalized = classification.strip().lower()
    if normalized == "bad_case":
        status = "suspected_hallucination"
        verdict = "bad_case"
        label = "bad_case"
    elif normalized == "preference":
        status = "reviewed"
        verdict = "ok"
        label = "preference"
    else:
        status = "reviewed"
        verdict = "ok"
        label = "unclear"

    url = (
        f"{settings.supabase_url}/rest/v1/ai_audits"
        f"?session_id=eq.{session_id}&message_id=eq.{corrected_message_id}"
    )
    payload = {
        "status": status,
        "verdict": verdict,
        "bad_case_id": bad_case_id,
        "analysis_label": label,
        "analysis_summary": summary,
        "triaged_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.patch(url, json=payload, headers=_headers(settings))
        if resp.status_code not in (200, 204):
            logger.warning("Failed finalizing ai_audits triage: %s", resp.text)
            return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("Exception finalizing ai_audits triage: %s", exc)
        return False

    return True
