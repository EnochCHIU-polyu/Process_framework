"""
POST /chat  — send a chat message, get an LLM response, persist to Supabase.

Supports two backends via the LLM_BACKEND setting:
  - "ollama"  — local Ollama server (no API key needed)
  - "openai"  — any OpenAI-compatible endpoint (Poe, OpenAI, Groq, etc.)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from process_framework.api.config import Settings, get_settings
from process_framework.api.feedback import build_session_guard, inject_guard_prompt
from process_framework.api.llm import call_llm

router = APIRouter()


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

    # --- Build message list, injecting audit guard for existing sessions ---
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    guard: Optional[str] = None
    if req.session_id:
        # Fetch any known bad cases / hallucination findings for this session
        # and prepend them as a system-level guard so the model avoids
        # repeating the same failures.
        guard = await build_session_guard(req.session_id, settings)
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

    return ChatResponse(
        session_id=session_id,
        assistant_message=assistant_text,
        assistant_message_id=assistant_message_id,
    )
