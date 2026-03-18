"""
Unified LLM caller for the PROCESS Chat Auditing API.

Supports two backends selected by ``settings.llm_backend``:

* ``"ollama"`` — calls a locally-running Ollama server via its native
  ``/api/chat`` endpoint (no external API key required).

* ``"openai"`` — uses the ``openai`` Python library against any
  OpenAI-compatible endpoint.  Works with:
    - Poe        (``OPENAI_BASE_URL=https://api.poe.com/v1``)
    - OpenAI     (``OPENAI_BASE_URL=https://api.openai.com/v1``)
    - Azure, Groq, Together AI, etc.

Usage::

    from process_framework.api.llm import call_llm
    text = await call_llm(messages=[{"role": "user", "content": "Hi"}],
                          settings=settings,
                          temperature=0.7)
"""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
from fastapi import HTTPException

from process_framework.api.config import Settings

# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


async def call_llm(
    messages: List[Dict[str, str]],
    settings: Settings,
    temperature: float = 0.7,
) -> str:
    """
    Call the configured LLM backend and return the assistant text.

    Args:
        messages:    OpenAI-style message list (``[{"role": ..., "content": ...}]``).
        settings:    Loaded :class:`Settings` instance.
        temperature: Sampling temperature passed to the model.

    Returns:
        The assistant's reply as a plain string.

    Raises:
        :class:`fastapi.HTTPException` (502/503) on upstream errors.
    """
    backend = settings.llm_backend.lower()
    if backend == "ollama":
        return await _call_ollama(messages, settings, temperature)
    if backend == "openai":
        return await _call_openai(messages, settings, temperature)
    raise HTTPException(
        status_code=500,
        detail=(
            f"Unknown LLM_BACKEND={settings.llm_backend!r}. "
            "Set it to 'ollama' or 'openai'."
        ),
    )


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------


async def _call_ollama(
    messages: List[Dict[str, str]],
    settings: Settings,
    temperature: float,
) -> str:
    payload: Dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
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

    return resp.json()["message"]["content"]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# OpenAI-compatible backend (Poe, OpenAI, Azure, Groq, …)
# ---------------------------------------------------------------------------


async def _call_openai(
    messages: List[Dict[str, str]],
    settings: Settings,
    temperature: float,
) -> str:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "LLM_BACKEND is set to 'openai' but OPENAI_API_KEY is not configured. "
                "Set OPENAI_API_KEY in your environment or .env file."
            ),
        )

    try:
        import openai  # noqa: PLC0415  (intentional lazy import — openai is optional)
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500,
            detail=(
                "The 'openai' package is not installed. "
                "Run: pip install 'process-framework[api]'"
            ),
        ) from exc

    try:
        aclient = openai.AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        completion = await aclient.chat.completions.create(
            model=settings.openai_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
        )
    except openai.APIConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach OpenAI-compatible API at {settings.openai_base_url}: {exc}",
        ) from exc
    except openai.AuthenticationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Authentication failed for OpenAI-compatible API: {exc}",
        ) from exc
    except openai.APIStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI-compatible API error {exc.status_code}: {exc.message}",
        ) from exc

    return completion.choices[0].message.content or ""
