"""
POST /chat  — send a chat message, get an LLM response, persist to Supabase.

Supports two backends via the LLM_BACKEND setting:
  - "ollama"  — local Ollama server (no API key needed)
  - "openai"  — any OpenAI-compatible endpoint (Poe, OpenAI, Groq, etc.)
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from learn_from_chat.orchestrator import process_feedback_and_learn
from process_framework.api.auto_audit import (
    persist_auto_audit_report,
    promote_bad_cases_from_report,
    run_auto_audit,
)
from process_framework.api.config import Settings, get_settings
from process_framework.api.feedback import build_session_guard, inject_guard_prompt
from process_framework.api.llm import call_llm

router = APIRouter()
logger = logging.getLogger(__name__)


def _brevity_mode_on(guard: Optional[str]) -> bool:
    return bool(guard and "BREVITY_MODE=ON" in guard)


def _is_too_long_response(text: str) -> bool:
    line_count = len([line for line in text.splitlines() if line.strip()])
    word_count = len(text.split())
    char_count = len(text)
    return line_count > 6 or word_count > 80 or char_count > 320


def _force_concise_output(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    bullet_like = [
        line
        for line in lines
        if re.match(r"^(?:[-*•]|\d+[\.)])\s*", line)
    ]
    if bullet_like:
        return "\n".join(bullet_like[:4])

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?\.])\s*", cleaned)
        if sentence.strip()
    ]
    if sentences:
        concise = " ".join(sentences[:4]).strip()
        if len(concise) > 240:
            return concise[:240].rstrip() + "…"
        return concise

    if len(cleaned) > 240:
        return cleaned[:240].rstrip() + "…"
    return cleaned


async def _rewrite_to_concise_if_needed(
    assistant_text: str,
    settings: Settings,
) -> str:
    if not _is_too_long_response(assistant_text):
        return assistant_text

    rewrite_messages = [
        {
            "role": "system",
            "content": (
                "Rewrite the answer to be concise and direct. "
                "Keep key facts only. "
                "Output max 4 bullet points or 4 short sentences. "
                "No preface and no extra sections."
            ),
        },
        {"role": "user", "content": assistant_text},
    ]
    rewritten = await call_llm(rewrite_messages, settings, temperature=0.0)
    candidate = rewritten or assistant_text
    if _is_too_long_response(candidate):
        return _force_concise_output(candidate)
    return candidate


async def _safe_process_feedback_learning(
    session_id: str,
    messages: List[ChatMessage],
    settings: Settings,
) -> Optional[str]:
    try:
        return await process_feedback_and_learn(
            session_id=session_id,
            messages=messages,
            settings=settings,
        )
    except Exception as exc:
        logger.warning("Feedback learning failed: %s", exc)
        return None


async def _safe_auto_audit_session(
    session_id: str,
    settings: Settings,
) -> None:
    try:
        result = await run_auto_audit(settings, session_id=session_id)
        if result.total_pairs_analyzed == 0:
            return
        async with httpx.AsyncClient(timeout=30.0) as client:
            await persist_auto_audit_report(client, settings, result)
            await promote_bad_cases_from_report(client, settings, result)
    except Exception as exc:
        logger.warning("Auto-audit background run failed for session %s: %s", session_id, exc)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    room_id: Optional[str] = None
    messages: List[ChatMessage]
    temperature: float = 0.7


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    assistant_message_id: str
    auto_bad_case_id: Optional[str] = None


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


async def _upsert_session(
    client: httpx.AsyncClient,
    settings: Settings,
    session_id: str,
    user_id: Optional[str],
    room_id: Optional[str],
) -> None:
    """Ensure a chat_sessions row exists."""
    url = f"{settings.supabase_url}/rest/v1/chat_sessions"
    payload = {
        "id": session_id,
        "user_id": user_id,
        "room_id": room_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post(
        url,
        json=payload,
        headers={
            **_supa_headers(settings),
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )
    if resp.status_code not in (200, 201, 204):
        raise HTTPException(
            status_code=502,
            detail=f"Supabase upsert session failed: {resp.text}",
        )


async def _insert_message(
    client: httpx.AsyncClient,
    settings: Settings,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """Insert a single chat_messages row."""
    url = f"{settings.supabase_url}/rest/v1/chat_messages"
    payload = {
        "id": message_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post(url, json=payload, headers=_supa_headers(settings))
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Supabase insert message failed: {resp.text}",
        )


async def _insert_audit(
    client: httpx.AsyncClient,
    settings: Settings,
    message_id: str,
    session_id: str,
    status: str = "pending",
) -> None:
    """Insert an ai_audits row tied to the assistant message."""
    url = f"{settings.supabase_url}/rest/v1/ai_audits"
    payload = {
        "id": str(uuid.uuid4()),
        "message_id": message_id,
        "session_id": session_id,
        "status": status,
        "verdict": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = await client.post(url, json=payload, headers=_supa_headers(settings))
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=502,
            detail=f"Supabase insert audit failed: {resp.text}",
        )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    settings: Settings = Depends(get_settings),
) -> Any:
    """
    Accept a conversation, call the configured LLM backend, persist to Supabase, return reply.

    - Backend is selected by ``LLM_BACKEND``: ``"ollama"`` (default) or ``"openai"``.
    - Both the last user message and the assistant reply are persisted.
    - An ``ai_audits`` row with ``status=pending`` is created automatically.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # --- Build message list, injecting audit guard for global learning ---
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    
    # Global Learning: Always build session guard regardless of session_id presence
    # Since build_session_guard also fetches global learned patterns, 
    # it ensures every chat session starts with historical knowledge.
    guard = await build_session_guard(session_id, settings)
    if guard:
        messages = inject_guard_prompt(messages, guard)

    # --- Call LLM (Ollama or OpenAI-compatible) ---
    effective_temperature = req.temperature
    if _brevity_mode_on(guard):
        effective_temperature = min(req.temperature, 0.2)

    assistant_text = await call_llm(messages, settings, effective_temperature)

    if _brevity_mode_on(guard):
        assistant_text = await _rewrite_to_concise_if_needed(assistant_text, settings)

    # --- Persist to Supabase ---
    async with httpx.AsyncClient(timeout=30.0) as client:
        await _upsert_session(
            client, settings, session_id, req.user_id, req.room_id
        )

        # Persist last user turn (skip if all messages are system/assistant)
        last_user_msg = next(
            (m for m in reversed(req.messages) if m.role == "user"), None
        )
        if last_user_msg:
            user_message_id = str(uuid.uuid4())
            await _insert_message(
                client, settings, user_message_id, session_id, "user", last_user_msg.content
            )

        # Persist assistant turn
        assistant_message_id = str(uuid.uuid4())
        await _insert_message(
            client, settings, assistant_message_id, session_id, "assistant", assistant_text
        )

        # Create audit record
        await _insert_audit(client, settings, assistant_message_id, session_id)

    # Run feedback-learning before response so auto-flag is reliable and visible to UI.
    auto_bad_case_id = await _safe_process_feedback_learning(
        session_id=session_id,
        messages=list(req.messages),
        settings=settings,
    )

    # Auto-run session audit (no button needed), keep non-blocking for chat latency.
    asyncio.create_task(_safe_auto_audit_session(session_id=session_id, settings=settings))

    return ChatResponse(
        session_id=session_id,
        assistant_message=assistant_text,
        assistant_message_id=assistant_message_id,
        auto_bad_case_id=auto_bad_case_id,
    )
