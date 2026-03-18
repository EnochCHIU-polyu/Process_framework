"""
POST /chat  — send a chat message, get Ollama response, persist to Supabase.
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
    Accept a conversation, call Ollama, persist to Supabase, return reply.

    - Ollama is called at ``OLLAMA_BASE_URL/api/chat``.
    - Both the last user message and the assistant reply are persisted.
    - An ``ai_audits`` row with ``status=pending`` is created automatically.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # Build Ollama payload
    ollama_payload: Dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": [{"role": m.role, "content": m.content} for m in req.messages],
        "stream": False,
        "options": {"temperature": req.temperature},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        # --- Call Ollama ---
        try:
            ollama_resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=ollama_payload,
            )
            ollama_resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama error {exc.response.status_code}: {exc.response.text}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot reach Ollama at {settings.ollama_base_url}: {exc}",
            ) from exc

        data = ollama_resp.json()
        assistant_text: str = data["message"]["content"]

        # --- Persist to Supabase ---
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
