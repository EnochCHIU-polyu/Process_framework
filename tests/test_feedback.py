"""
Tests for process_framework.api.feedback

Covers:
- build_guard_prompt() — pure function converting bad-case records to a system message
- inject_guard_prompt() — injects guard into message list (with/without system message)
- fetch_session_bad_cases() — async Supabase fetch with graceful failure handling
- build_session_guard()     — end-to-end convenience function
- /chat route — guard prompt is injected when session has bad cases
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from process_framework.api.feedback import (
    build_guard_prompt,
    build_session_guard,
    fetch_session_bad_cases,
    inject_guard_prompt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings():
    s = MagicMock()
    s.supabase_url = "https://test.supabase.co"
    s.supabase_service_role_key = "test-key"
    return s


def _http_response(body: Any, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    return resp


def _async_client_ctx(get_resp: MagicMock) -> MagicMock:
    """Mock httpx.AsyncClient context manager that returns *get_resp* for GET."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# build_guard_prompt()
# ---------------------------------------------------------------------------


class TestBuildGuardPrompt:
    def test_empty_list_returns_empty_string(self):
        assert build_guard_prompt([], []) == ""

    def test_single_hallucination_bad_case(self):
        bad_cases = [{"category": "hallucination", "reason": "Stated wrong capital city"}]
        result = build_guard_prompt(bad_cases)
        assert "HALLUCINATION" in result
        assert "global audit knowledge" in result.lower()

    def test_includes_expected_output_when_present(self):
        bad_cases = [
            {
                "category": "factual",
                "reason": "Wrong price",
                "expected_output": "The price is $99",
            }
        ]
        result = build_guard_prompt(bad_cases)
        assert "The price is $99" in result

    def test_multiple_bad_cases_weighting(self):
        bad_cases = [
            {"category": "hallucination", "reason": "First issue"},
            {"category": "hallucination", "reason": "Second issue"},
        ]
        result = build_guard_prompt(bad_cases)
        assert "HALLUCINATION" in result
        assert "x2" in result

    def test_brevity_mode_trigger_fresh(self):
        bad_cases = [{"category": "user_experience", "reason": "too long response"}]
        result = build_guard_prompt(bad_cases)
        assert "BREVITY_MODE=ON" in result
        assert "PLAINTEXT_MODE=ON" in result

    def test_brevity_mode_trigger_learned(self):
        learned = [{"category": "user_experience", "pattern_description": "verbose output"}]
        result = build_guard_prompt([], learned)
        assert "BREVITY_MODE=ON" in result
        assert "PLAINTEXT_MODE=ON" in result

    def test_none_fields_are_handled_gracefully(self):
        bad_cases = [
            {
                "category": "hallucination",
                "reason": "Bad answer",
                "root_cause": None,
                "expected_output": None,
                "ignored_keywords": None,
            }
        ]
        result = build_guard_prompt(bad_cases)
        assert "HALLUCINATION" in result

    def test_missing_category_defaults_gracefully(self):
        bad_cases = [{"reason": "Some issue"}]
        result = build_guard_prompt(bad_cases)
        assert "PROCESS-LOOP" in result

    def test_all_categories_have_labels(self):
        categories = [
            ("hallucination", "HALLUCINATION"),
            ("intent_understanding", "INTENT / CONSTRAINT MISSED"),
            ("user_experience", "USER EXPERIENCE"),
            ("factual", "FACTUAL ERROR"),
            ("logical", "LOGICAL ERROR"),
            ("referential", "REFERENTIAL ERROR"),
        ]
        for cat, label in categories:
            bad_cases = [{"category": cat, "reason": "test"}]
            result = build_guard_prompt(bad_cases)
            assert label in result, f"Label {label!r} not found for category {cat!r}"

    def test_footer_contains_hallucination_prevention_guidance(self):
        bad_cases = [{"category": "hallucination", "reason": "Made up fact"}]
        result = build_guard_prompt(bad_cases)
        assert "hallucination" in result.lower()
        assert "fabricate" in result.lower()

    def test_none_fields_are_handled_gracefully(self):
        bad_cases = [
            {
                "category": "hallucination",
                "reason": "Bad answer",
                "root_cause": None,
                "expected_output": None,
                "ignored_keywords": None,
            }
        ]
        result = build_guard_prompt(bad_cases)
        assert "HALLUCINATION" in result

    def test_missing_category_defaults_gracefully(self):
        bad_cases = [{"reason": "Some issue"}]
        result = build_guard_prompt(bad_cases)
        assert "PROCESS-LOOP" in result
    def test_prepends_system_message_when_none_exists(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = inject_guard_prompt(messages, "Guard text")
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "Guard text"
        assert result[1]["role"] == "user"

    def test_augments_existing_system_message(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        result = inject_guard_prompt(messages, "Guard text")
        assert result[0]["role"] == "system"
        assert "You are helpful." in result[0]["content"]
        assert "Guard text" in result[0]["content"]
        assert len(result) == 2  # no extra messages added

    def test_empty_guard_text_returns_original_list(self):
        messages = [{"role": "user", "content": "Hi"}]
        result = inject_guard_prompt(messages, "")
        assert result is messages

    def test_does_not_mutate_original_list(self):
        messages = [{"role": "user", "content": "Hello"}]
        original_id = id(messages)
        inject_guard_prompt(messages, "Guard text")
        assert id(messages) == original_id
        assert len(messages) == 1  # unchanged

    def test_does_not_mutate_existing_system_message_dict(self):
        sys_msg = {"role": "system", "content": "Original."}
        messages = [sys_msg, {"role": "user", "content": "Hi"}]
        inject_guard_prompt(messages, "Guard")
        # Original dict must remain unchanged
        assert sys_msg["content"] == "Original."

    def test_preserves_all_messages_after_guard(self):
        messages = [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "B"},
            {"role": "user", "content": "C"},
        ]
        result = inject_guard_prompt(messages, "Guard")
        assert len(result) == 4
        assert result[0]["role"] == "system"
        assert result[1] == messages[0]
        assert result[2] == messages[1]
        assert result[3] == messages[2]


# ---------------------------------------------------------------------------
# fetch_session_bad_cases()
# ---------------------------------------------------------------------------


class TestFetchSessionBadCases:
    @pytest.mark.asyncio
    async def test_returns_bad_cases_on_200(self):
        bad_cases = [
            {"category": "hallucination", "reason": "Wrong fact", "ignored_keywords": []}
        ]
        with patch(
            "process_framework.api.feedback.httpx.AsyncClient",
            return_value=_async_client_ctx(_http_response(bad_cases, 200)),
        ):
            result = await fetch_session_bad_cases("sess-1", _mock_settings())
        assert result == bad_cases

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_non_200(self):
        with patch(
            "process_framework.api.feedback.httpx.AsyncClient",
            return_value=_async_client_ctx(_http_response([], 404)),
        ):
            result = await fetch_session_bad_cases("sess-1", _mock_settings())
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_network_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("process_framework.api.feedback.httpx.AsyncClient", return_value=cm):
            result = await fetch_session_bad_cases("sess-err", _mock_settings())
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_null_json(self):
        with patch(
            "process_framework.api.feedback.httpx.AsyncClient",
            return_value=_async_client_ctx(_http_response(None, 200)),
        ):
            result = await fetch_session_bad_cases("sess-1", _mock_settings())
        assert result == []


# ---------------------------------------------------------------------------
# build_session_guard()
# ---------------------------------------------------------------------------


class TestBuildSessionGuard:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_bad_cases(self):
        with patch(
            "process_framework.api.feedback.fetch_session_bad_cases",
            new=AsyncMock(return_value=[]),
        ):
            result = await build_session_guard("sess-1", _mock_settings())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_guard_string_when_bad_cases_exist(self):
        bad_cases = [{"category": "hallucination", "reason": "Wrong answer"}]
        with patch(
            "process_framework.api.feedback.fetch_session_bad_cases",
            new=AsyncMock(return_value=bad_cases),
        ):
            result = await build_session_guard("sess-1", _mock_settings())
        assert result is not None
        assert "PROCESS-LOOP" in result
        assert "GLOBAL AUDIT KNOWLEDGE" in result


# ---------------------------------------------------------------------------
# /chat route — guard prompt integration
# ---------------------------------------------------------------------------


@pytest.fixture()
def chat_client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")
    from fastapi.testclient import TestClient
    from process_framework.api.main import app
    return TestClient(app, raise_server_exceptions=True)


def _supa_async_client_post_only(*post_resps):
    """Mock httpx.AsyncClient that handles only POST calls (for Supabase writes)."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=list(post_resps))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _insert_ok():
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = []
    resp.text = "[]"
    return resp


class TestChatGuardIntegration:
    def test_guard_injected_when_session_has_bad_cases(self, chat_client):
        """When bad cases exist the guard prompt is prepended to the LLM messages."""
        bad_cases = [
            {"category": "hallucination", "reason": "Stated wrong date", "ignored_keywords": []}
        ]
        captured_messages = []

        async def _fake_llm(messages, settings, temperature=0.7):
            captured_messages.extend(messages)
            return "Corrected answer."

        with (
            patch("process_framework.api.routes.chat.call_llm", new=_fake_llm),
            patch(
                "process_framework.api.routes.chat.build_session_guard",
                new=AsyncMock(return_value=build_guard_prompt(bad_cases)),
            ),
            patch("process_framework.api.routes.chat.inject_guard_prompt", wraps=inject_guard_prompt),
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client_post_only(
                _insert_ok(),  # upsert session
                _insert_ok(),  # insert user message
                _insert_ok(),  # insert assistant message
                _insert_ok(),  # insert audit
            )
            resp = chat_client.post(
                "/chat",
                json={
                    "session_id": "existing-session-001",
                    "messages": [{"role": "user", "content": "Tell me about the event."}],
                },
            )

        assert resp.status_code == 200
        # The first message sent to the LLM must be a system guard
        assert captured_messages[0]["role"] == "system"
        assert "GLOBAL AUDIT KNOWLEDGE" in captured_messages[0]["content"]

    def test_global_guard_always_called(self, chat_client):
        """Even new sessions should now fetch global learned patterns."""
        with (
            patch("process_framework.api.routes.chat.call_llm", new=AsyncMock(return_value="Hello!")),
            patch(
                "process_framework.api.routes.chat.build_session_guard",
                new=AsyncMock(return_value="Global Policy"),
            ) as mock_guard,
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client_post_only(
                _insert_ok(),
                _insert_ok(),
                _insert_ok(),
                _insert_ok(),
            )
            resp = chat_client.post(
                "/chat",
                json={"messages": [{"role": "user", "content": "Hi"}]},
            )

        assert resp.status_code == 200
        # build_session_guard SHOULD be called now (global learning)
        mock_guard.assert_called()

    def test_chat_proceeds_when_no_bad_cases(self, chat_client):
        """When the session has no bad cases the LLM is called without a guard."""
        captured_messages = []

        async def _fake_llm(messages, settings, temperature=0.7):
            captured_messages.extend(messages)
            return "Normal answer."

        with (
            patch("process_framework.api.routes.chat.call_llm", new=_fake_llm),
            patch(
                "process_framework.api.routes.chat.build_session_guard",
                new=AsyncMock(return_value=None),
            ),
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client_post_only(
                _insert_ok(),
                _insert_ok(),
                _insert_ok(),
                _insert_ok(),
            )
            resp = chat_client.post(
                "/chat",
                json={
                    "session_id": "clean-session",
                    "messages": [{"role": "user", "content": "What is 2+2?"}],
                },
            )

        assert resp.status_code == 200
        # No system guard should be prepended
        assert all(m["role"] != "system" or "AUDIT FEEDBACK" not in m.get("content", "") for m in captured_messages)

    def test_existing_system_message_is_augmented_not_replaced(self, chat_client):
        """Guard is appended to an existing system message, not added as a separate one."""
        bad_cases = [{"category": "factual", "reason": "Wrong year"}]
        captured_messages = []

        async def _fake_llm(messages, settings, temperature=0.7):
            captured_messages.extend(messages)
            return "Updated answer."

        with (
            patch("process_framework.api.routes.chat.call_llm", new=_fake_llm),
            patch(
                "process_framework.api.routes.chat.build_session_guard",
                new=AsyncMock(return_value=build_guard_prompt(bad_cases)),
            ),
            patch("process_framework.api.routes.chat.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.return_value = _supa_async_client_post_only(
                _insert_ok(),
                _insert_ok(),
                _insert_ok(),
                _insert_ok(),
            )
            resp = chat_client.post(
                "/chat",
                json={
                    "session_id": "sess-with-system",
                    "messages": [
                        {"role": "system", "content": "You are a specialist."},
                        {"role": "user", "content": "When did X happen?"},
                    ],
                },
            )

        assert resp.status_code == 200
        # The first message should be the augmented system message
        sys_msgs = [m for m in captured_messages if m["role"] == "system"]
        assert len(sys_msgs) == 1
        content = sys_msgs[0]["content"]
        assert "You are a specialist." in content
        assert "GLOBAL AUDIT KNOWLEDGE" in content
