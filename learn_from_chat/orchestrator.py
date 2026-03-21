from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple
from urllib.parse import quote

import httpx

from learn_from_chat.correction_extractor import extract_correction, triage_feedback
from learn_from_chat.db_handler import (
    attach_feedback_context_to_audit,
    finalize_audit_triage,
    save_user_correction,
)
from learn_from_chat.sentiment import SentimentAnalyzer
from process_framework.api.config import Settings

logger = logging.getLogger(__name__)

sentiment_analyzer = SentimentAnalyzer()


def _build_fallback_correction(user_feedback: str) -> dict:
    feedback_lower = user_feedback.lower()
    is_factual = any(token in feedback_lower for token in ("wrong", "incorrect", "not true", "hallucination", "false"))
    return {
        "is_correction": True,
        "error_type": "factual_error" if is_factual else "tone_issue",
        "correct_answer": None,
        "reason": "User strongly disagreed with the assistant response.",
        "ignored_keywords": [],
    }


def _extract_feedback_context(messages: Sequence[object]) -> Optional[Tuple[str, str, str]]:
    roles: List[Tuple[str, str]] = []
    for item in messages:
        role = getattr(item, "role", None)
        content = getattr(item, "content", None)
        if isinstance(role, str) and isinstance(content, str):
            roles.append((role, content))

    if len(roles) < 2:
        return None
    if roles[-1][0] != "user":
        return None

    user_feedback = roles[-1][1]

    assistant_index = None
    for index in range(len(roles) - 2, -1, -1):
        if roles[index][0] == "assistant":
            assistant_index = index
            break
    if assistant_index is None:
        return None

    assistant_answer = roles[assistant_index][1]

    user_question = ""
    for index in range(assistant_index - 1, -1, -1):
        if roles[index][0] == "user":
            user_question = roles[index][1]
            break

    return user_question, assistant_answer, user_feedback


async def _resolve_corrected_message_id(session_id: str, settings: Settings) -> Optional[str]:
    encoded_session_id = quote(session_id, safe="")
    url = (
        f"{settings.supabase_url}/rest/v1/chat_messages"
        f"?session_id=eq.{encoded_session_id}&role=eq.assistant&select=id,created_at&order=created_at.desc&limit=2"
    )
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("Failed to resolve corrected message id: %s", resp.text)
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        if len(data) >= 2:
            return str(data[1].get("id"))
        return str(data[0].get("id"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error resolving corrected message id: %s", exc)
        return None


async def process_feedback_and_learn(
    session_id: str,
    messages: Sequence[object],
    settings: Settings,
) -> Optional[str]:
    context = _extract_feedback_context(messages)
    if not context:
        logger.info("Feedback learning skipped: no valid user-feedback context found.")
        return None

    user_question, assistant_answer, user_feedback = context

    if not sentiment_analyzer.is_dissatisfied(user_feedback):
        logger.info("Feedback learning skipped: sentiment not dissatisfied.")
        return None

    correction = await extract_correction(
        user_question=user_question,
        assistant_answer=assistant_answer,
        user_feedback=user_feedback,
        settings=settings,
    )
    if not correction:
        correction = _build_fallback_correction(user_feedback)
        logger.info("Extractor returned no correction; using fallback bad-case payload.")

    corrected_message_id = await _resolve_corrected_message_id(session_id, settings)
    if not corrected_message_id:
        logger.warning("Feedback learning skipped: unable to resolve corrected assistant message id.")
        return None

    await attach_feedback_context_to_audit(
        session_id=session_id,
        corrected_message_id=corrected_message_id,
        user_question=user_question,
        assistant_answer=assistant_answer,
        user_feedback=user_feedback,
        settings=settings,
    )

    triage = await triage_feedback(
        user_question=user_question,
        assistant_answer=assistant_answer,
        user_feedback=user_feedback,
        settings=settings,
    )

    if not triage:
        triage = {
            "classification": "unclear",
            "error_type": correction.get("error_type", "other"),
            "summary": "Triage model unavailable; classified as unclear for manual review.",
            "confidence": 0.3,
            "correct_answer": correction.get("correct_answer"),
            "ignored_keywords": correction.get("ignored_keywords", []),
        }

    classification = str(triage.get("classification", "unclear"))
    if classification != "bad_case":
        await finalize_audit_triage(
            session_id=session_id,
            corrected_message_id=corrected_message_id,
            classification=classification,
            summary=str(triage.get("summary", "Marked as non-bad-case preference/unclear.")),
            settings=settings,
            bad_case_id=None,
        )
        logger.info("Feedback triaged as %s; no bad_case row created.", classification)
        return None

    saved_id = await save_user_correction(
        session_id=session_id,
        corrected_message_id=corrected_message_id,
        user_question=user_question,
        assistant_answer=assistant_answer,
        user_feedback=user_feedback,
        correction_data={
            **correction,
            "error_type": str(triage.get("error_type", correction.get("error_type", "other"))),
            "correct_answer": triage.get("correct_answer", correction.get("correct_answer")),
            "reason": str(triage.get("summary", correction.get("reason", "User correction detected."))),
            "ignored_keywords": triage.get("ignored_keywords", correction.get("ignored_keywords", [])),
        },
        settings=settings,
    )

    if saved_id:
        await finalize_audit_triage(
            session_id=session_id,
            corrected_message_id=corrected_message_id,
            classification="bad_case",
            summary=str(triage.get("summary", "Classified as factual/model error.")),
            settings=settings,
            bad_case_id=saved_id,
        )
        logger.info("Captured feedback learning case: %s", saved_id)
        return saved_id
    else:
        logger.warning("Failed to persist feedback learning case to bad_cases.")
        return None
