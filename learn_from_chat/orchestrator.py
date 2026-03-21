from __future__ import annotations

import logging
from typing import List, Optional, Sequence, Tuple

import httpx

from learn_from_chat.correction_extractor import extract_correction
from learn_from_chat.db_handler import save_user_correction
from learn_from_chat.sentiment import SentimentAnalyzer
from process_framework.api.config import Settings

logger = logging.getLogger(__name__)

sentiment_analyzer = SentimentAnalyzer()


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
    url = (
        f"{settings.supabase_url}/rest/v1/chat_messages"
        f"?session_id=eq.{session_id}&role=eq.assistant&select=id,created_at&order=created_at.desc&limit=2"
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
) -> None:
    context = _extract_feedback_context(messages)
    if not context:
        return

    user_question, assistant_answer, user_feedback = context

    if not sentiment_analyzer.is_dissatisfied(user_feedback):
        return

    correction = await extract_correction(
        user_question=user_question,
        assistant_answer=assistant_answer,
        user_feedback=user_feedback,
        settings=settings,
    )
    if not correction:
        return

    corrected_message_id = await _resolve_corrected_message_id(session_id, settings)
    if not corrected_message_id:
        return

    saved_id = await save_user_correction(
        session_id=session_id,
        corrected_message_id=corrected_message_id,
        user_question=user_question,
        assistant_answer=assistant_answer,
        user_feedback=user_feedback,
        correction_data=correction,
        settings=settings,
    )

    if saved_id:
        logger.info("Captured feedback learning case: %s", saved_id)
