"""
Tests for the PROCESS Chat Auditing API endpoints.

All external HTTP calls (Ollama, Supabase, OpenAI) are mocked so the tests run
without any live services.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers to stub Supabase responses
# ---------------------------------------------------------------------------

def _ok_response(body: Any, status_code: int = 201) -> MagicMock:
    """Return a mock httpx.Response with json() → body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.raise_for_status = MagicMock()
    return resp


def _supabase_insert_ok() -> MagicMock:
    return _ok_response([], 201)


def _supabase_session_ok() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = []
    resp.text = "[]"
    return resp


def _supa_async_client(*responses):
    """Build a mock httpx.AsyncClient context manager for Supabase calls only."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=list(responses))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    """TestClient with env vars patched so Settings can load (Ollama backend)."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    # Import app AFTER env vars are set
    from process_framework.api.main import app
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def openai_client(monkeypatch):
    """TestClient configured to use the OpenAI-compatible backend."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-poe-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.poe.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek-v3.2")

    from process_framework.api.main import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["llm_backend"] == "ollama"


def test_health_openai_backend(openai_client):
    resp = openai_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["llm_backend"] == "openai"


# ---------------------------------------------------------------------------
# POST /chat  —  Ollama backend
# ---------------------------------------------------------------------------


class TestChat:
    def test_chat_returns_assistant_message(self, client):
        with (
            patch("process_framework.api.routes.chat.call_llm", new=AsyncMock(return_value="Paris is the capital of France.")),
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client(
                _supabase_session_ok(),   # upsert session
                _supabase_insert_ok(),    # insert user message
                _supabase_insert_ok(),    # insert assistant message
                _supabase_insert_ok(),    # insert audit
            )
            resp = client.post(
                "/chat",
                json={"messages": [{"role": "user", "content": "Capital of France?"}]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assistant_message"] == "Paris is the capital of France."
        assert "session_id" in data
        assert "assistant_message_id" in data

    def test_chat_reuses_provided_session_id(self, client):
        session_id = "aaaabbbb-0000-0000-0000-000000000001"
        with (
            patch("process_framework.api.routes.chat.call_llm", new=AsyncMock(return_value="Hello!")),
            patch("process_framework.api.routes.chat.build_session_guard", new=AsyncMock(return_value=None)),
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client(
                _supabase_session_ok(),
                _supabase_insert_ok(),
                _supabase_insert_ok(),
                _supabase_insert_ok(),
            )
            resp = client.post(
                "/chat",
                json={
                    "session_id": session_id,
                    "messages": [{"role": "user", "content": "Hi"}],
                },
            )

        assert resp.status_code == 200
        assert resp.json()["session_id"] == session_id

    def test_chat_llm_error_propagates(self, client):
        from fastapi import HTTPException

        async def _failing_llm(*args, **kwargs):
            raise HTTPException(status_code=503, detail="Cannot reach Ollama at http://localhost:11434: Connection refused")

        with patch("process_framework.api.routes.chat.call_llm", new=_failing_llm):
            resp = client.post(
                "/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )

        assert resp.status_code == 503
        assert "Ollama" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /chat  —  OpenAI-compatible backend (Poe)
# ---------------------------------------------------------------------------


class TestChatOpenAI:
    def test_chat_openai_backend_returns_message(self, openai_client):
        """OpenAI-compatible path returns assistant text from the mock."""
        with (
            patch("process_framework.api.routes.chat.call_llm", new=AsyncMock(return_value="黑洞是宇宙中引力最強的地方。")),
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client(
                _supabase_session_ok(),
                _supabase_insert_ok(),
                _supabase_insert_ok(),
                _supabase_insert_ok(),
            )
            resp = openai_client.post(
                "/chat",
                json={"messages": [{"role": "user", "content": "用一個10歲孩子也能理解的方式解釋黑洞的概念"}]},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["assistant_message"] == "黑洞是宇宙中引力最強的地方。"
        assert "assistant_message_id" in data

    def test_chat_openai_missing_api_key_returns_500(self, monkeypatch):
        """Missing OPENAI_API_KEY with openai backend → 500."""
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
        monkeypatch.setenv("LLM_BACKEND", "openai")
        # Deliberately do NOT set OPENAI_API_KEY

        from process_framework.api.main import app
        test_client = TestClient(app, raise_server_exceptions=False)
        resp = test_client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )
        assert resp.status_code == 500
        assert "OPENAI_API_KEY" in resp.json()["detail"]

    def test_chat_openai_connection_error_returns_503(self, openai_client):
        """Network failure on the OpenAI endpoint → 503."""
        from fastapi import HTTPException

        async def _conn_error(*args, **kwargs):
            raise HTTPException(status_code=503, detail="Cannot reach OpenAI-compatible API at https://api.poe.com/v1: unreachable")

        with patch("process_framework.api.routes.chat.call_llm", new=_conn_error):
            resp = openai_client.post(
                "/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )

        assert resp.status_code == 503

    def test_llm_backend_unknown_returns_500(self, monkeypatch):
        """Unknown LLM_BACKEND value → 500."""
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
        monkeypatch.setenv("LLM_BACKEND", "unknown_backend")

        from process_framework.api.main import app
        test_client = TestClient(app, raise_server_exceptions=False)
        resp = test_client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )
        assert resp.status_code == 500
        assert "LLM_BACKEND" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /audit/{message_id}/mark-bad
# ---------------------------------------------------------------------------


class TestAuditEndpoint:
    def _make_async_client(self, fetch_resp, *insert_resps):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=fetch_resp)
        mock_client.post = AsyncMock(side_effect=list(insert_resps))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    def _message_fetch_ok(self, message_id: str = "msg-001", session_id: str = "sess-001"):
        return _ok_response(
            [{"id": message_id, "session_id": session_id, "role": "assistant", "content": "Bad answer"}],
            200,
        )

    def test_mark_bad_returns_ids(self, client):
        msg_id = "aaaabbbb-0000-0000-0000-000000000002"
        with patch("process_framework.api.routes.audit.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = self._make_async_client(
                self._message_fetch_ok(msg_id),
                _supabase_insert_ok(),  # bad_cases
                _supabase_insert_ok(),  # ai_audits
            )
            resp = client.post(
                f"/audit/{msg_id}/mark-bad",
                json={"reason": "Fabricated fact", "category": "hallucination"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["message_id"] == msg_id
        assert data["status"] == "bad_case"
        assert "bad_case_id" in data
        assert "audit_id" in data

    def test_mark_bad_message_not_found_returns_404(self, client):
        with patch("process_framework.api.routes.audit.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_ok_response([], 200))
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=mock_client)
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = cm

            resp = client.post(
                "/audit/nonexistent-id/mark-bad",
                json={"reason": "test"},
            )

        assert resp.status_code == 404
