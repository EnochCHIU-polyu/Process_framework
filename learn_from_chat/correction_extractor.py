from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from process_framework.api.config import Settings
from process_framework.api.llm import call_llm

logger = logging.getLogger(__name__)

_PROMPT = """You analyze user feedback for LLM answer quality.

Given:
- User question
- Assistant answer
- User feedback

Extract whether the user is correcting the assistant and return JSON only with keys:
{
  "is_correction": boolean,
  "error_type": "hallucination" | "factual_error" | "intent_misunderstanding" | "constraint_ignored" | "tone_issue" | "other",
  "correct_answer": string | null,
  "reason": string,
  "ignored_keywords": string[]
}

Rules:
- is_correction=true only when user clearly indicates answer is wrong/misleading/incomplete.
- If no explicit corrected fact is present, keep correct_answer null.
- ignored_keywords should contain short constraints user expected (if any), otherwise []
- Return strict JSON object, no markdown.

User question:
{user_question}

Assistant answer:
{assistant_answer}

User feedback:
{user_feedback}
"""


def _extract_json(raw: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def extract_correction(
    user_question: str,
    assistant_answer: str,
    user_feedback: str,
    settings: Settings,
) -> Optional[Dict[str, Any]]:
    prompt = _PROMPT.format(
        user_question=user_question.strip(),
        assistant_answer=assistant_answer.strip(),
        user_feedback=user_feedback.strip(),
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await call_llm(messages, settings, temperature=0.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Correction extraction failed: %s", exc)
        return None

    data = _extract_json(raw)
    if not data:
        return None

    is_correction = bool(data.get("is_correction", False))
    if not is_correction:
        return None

    ignored_keywords = data.get("ignored_keywords")
    if not isinstance(ignored_keywords, list):
        ignored_keywords = []

    return {
        "is_correction": True,
        "error_type": str(data.get("error_type", "other")),
        "correct_answer": data.get("correct_answer"),
        "reason": str(data.get("reason", "User indicated answer quality issue.")),
        "ignored_keywords": [str(item).strip() for item in ignored_keywords if str(item).strip()],
    }
