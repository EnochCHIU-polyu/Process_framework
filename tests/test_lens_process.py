"""
Tests for LENS-aligned enhancements to the PROCESS framework.

Covers:
- New BadCaseCategory LENS values (FACTUAL, LOGICAL, REFERENTIAL)
- New EvaluationDimension LENS values (FACTUAL_GROUNDING, SEMANTIC_CORRECTNESS,
  REASONING_QUALITY)
- llm_judge._parse_scores() parsing logic
- llm_judge_evaluate() error handling
- /process/run/{session_id}?auto_evaluate=true endpoint
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from process_framework.core.enums import BadCaseCategory, EvaluationDimension
from process_framework.api.llm_judge import _parse_scores, JUDGE_DIMENSIONS
from tests.helpers import ok_response, supabase_insert_ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_process_async_client(messages_resp, bad_cases_resp, *persist_resps):
    """
    Build a mock httpx.AsyncClient context manager that handles the two
    GET calls (messages + bad_cases) and the POST call (persist report).
    """
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[messages_resp, bad_cases_resp])
    mock_client.post = AsyncMock(side_effect=list(persist_resps))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.fixture()
def process_client(monkeypatch):
    """TestClient for process/run tests (Ollama backend)."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1:8b")

    from process_framework.api.main import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# LENS enum values
# ---------------------------------------------------------------------------


class TestLENSBadCaseCategories:
    """New LENS-aligned BadCaseCategory values are present and parseable."""

    def test_factual_category_exists(self):
        assert BadCaseCategory.FACTUAL.value == "factual"

    def test_logical_category_exists(self):
        assert BadCaseCategory.LOGICAL.value == "logical"

    def test_referential_category_exists(self):
        assert BadCaseCategory.REFERENTIAL.value == "referential"

    def test_lens_categories_parseable_from_string(self):
        for value in ("factual", "logical", "referential"):
            cat = BadCaseCategory(value)
            assert cat.value == value

    def test_original_categories_still_present(self):
        """Ensure backward-compatible categories are unchanged."""
        assert BadCaseCategory.HALLUCINATION.value == "hallucination"
        assert BadCaseCategory.INTENT_UNDERSTANDING.value == "intent_understanding"
        assert BadCaseCategory.USER_EXPERIENCE.value == "user_experience"


class TestLENSEvaluationDimensions:
    """New LENS-aligned EvaluationDimension values are present and parseable."""

    def test_factual_grounding_exists(self):
        assert EvaluationDimension.FACTUAL_GROUNDING.value == "factual_grounding"

    def test_semantic_correctness_exists(self):
        assert EvaluationDimension.SEMANTIC_CORRECTNESS.value == "semantic_correctness"

    def test_reasoning_quality_exists(self):
        assert EvaluationDimension.REASONING_QUALITY.value == "reasoning_quality"

    def test_lens_dimensions_parseable_from_string(self):
        for value in ("factual_grounding", "semantic_correctness", "reasoning_quality"):
            dim = EvaluationDimension(value)
            assert dim.value == value

    def test_lens_dimensions_in_judge_dimensions_constant(self):
        """JUDGE_DIMENSIONS tuple contains all three LENS dimensions."""
        assert "factual_grounding" in JUDGE_DIMENSIONS
        assert "semantic_correctness" in JUDGE_DIMENSIONS
        assert "reasoning_quality" in JUDGE_DIMENSIONS

    def test_original_dimensions_still_present(self):
        """Ensure backward-compatible dimensions are unchanged."""
        assert EvaluationDimension.ANSWER_ACCURACY.value == "answer_accuracy"
        assert EvaluationDimension.HALLUCINATION_LEVEL.value == "hallucination_level"


# ---------------------------------------------------------------------------
# _parse_scores()
# ---------------------------------------------------------------------------


class TestParseScores:
    """Unit-tests for the JSON score parser in llm_judge."""

    def test_parses_valid_json(self):
        raw = '{"factual_grounding": 5, "semantic_correctness": 4, "reasoning_quality": 3}'
        scores = _parse_scores(raw)
        assert scores["factual_grounding"] == 5
        assert scores["semantic_correctness"] == 4
        assert scores["reasoning_quality"] == 3

    def test_ignores_prose_around_json(self):
        raw = "Sure, here are the scores:\n{\"factual_grounding\": 4, \"semantic_correctness\": 5} Great!"
        scores = _parse_scores(raw)
        assert scores["factual_grounding"] == 4
        assert scores["semantic_correctness"] == 5

    def test_rejects_out_of_range_scores(self):
        raw = '{"factual_grounding": 6, "semantic_correctness": 0}'
        scores = _parse_scores(raw)
        assert "factual_grounding" not in scores
        assert "semantic_correctness" not in scores

    def test_skips_unknown_dimensions(self):
        raw = '{"factual_grounding": 4, "unknown_dim": 3}'
        scores = _parse_scores(raw)
        assert scores["factual_grounding"] == 4
        assert "unknown_dim" not in scores

    def test_returns_empty_on_no_json(self):
        scores = _parse_scores("No JSON here at all.")
        assert scores == {}

    def test_returns_empty_on_invalid_json(self):
        scores = _parse_scores("{broken json")
        assert scores == {}

    def test_all_judge_dimensions_extracted(self):
        payload = {dim: 4 for dim in JUDGE_DIMENSIONS}
        raw = json.dumps(payload)
        scores = _parse_scores(raw)
        for dim in JUDGE_DIMENSIONS:
            assert scores[dim] == 4


# ---------------------------------------------------------------------------
# /process/run/{session_id}  — without auto_evaluate (existing behaviour)
# ---------------------------------------------------------------------------


class TestProcessRun:
    def _messages(self, session_id: str = "sess-1"):
        return ok_response(
            [
                {"id": "msg-1", "role": "user", "content": "What is a black hole?", "created_at": "2024-01-01T00:00:00Z"},
                {"id": "msg-2", "role": "assistant", "content": "A black hole is a region of spacetime.", "created_at": "2024-01-01T00:00:01Z"},
            ],
            200,
        )

    def _bad_cases(self):
        return ok_response([], 200)

    def test_process_run_without_auto_evaluate(self, process_client):
        with patch("process_framework.api.routes.process.httpx.AsyncClient") as mock_cls:
            mock_cls.side_effect = [
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
            ]
            resp = process_client.post("/process/run/sess-1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess-1"
        assert data["total_cases"] == 1
        assert data["auto_evaluated"] is False

    def test_process_run_no_messages_returns_404(self, process_client):
        with patch("process_framework.api.routes.process.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = _make_process_async_client(
                ok_response([], 200),
                ok_response([], 200),
            )
            resp = process_client.post("/process/run/empty-session")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /process/run/{session_id}?auto_evaluate=true
# ---------------------------------------------------------------------------


class TestProcessRunAutoEvaluate:
    def _messages(self):
        return ok_response(
            [
                {"id": "msg-u1", "role": "user", "content": "解釋黑洞的概念", "created_at": "2024-01-01T00:00:00Z"},
                {"id": "msg-a1", "role": "assistant", "content": "黑洞是引力極強的天體。", "created_at": "2024-01-01T00:00:01Z"},
            ],
            200,
        )

    def _bad_cases(self):
        return ok_response([], 200)

    def test_auto_evaluate_calls_llm_judge(self, process_client):
        """auto_evaluate=true triggers llm_judge_evaluate and sets auto_evaluated=True."""
        judge_scores = {
            "factual_grounding": 5,
            "semantic_correctness": 5,
            "reasoning_quality": 4,
            "hallucination_level": 5,
            "answer_accuracy": 4,
        }
        with (
            patch(
                "process_framework.api.routes.process.llm_judge_evaluate",
                new=AsyncMock(return_value=judge_scores),
            ),
            patch("process_framework.api.routes.process.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.side_effect = [
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
            ]
            resp = process_client.post("/process/run/sess-auto?auto_evaluate=true")

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_evaluated"] is True
        assert data["total_cases"] == 1

    def test_auto_evaluate_false_by_default(self, process_client):
        """auto_evaluate defaults to False; llm_judge_evaluate is NOT called."""
        with (
            patch(
                "process_framework.api.routes.process.llm_judge_evaluate",
                new=AsyncMock(return_value={}),
            ) as mock_judge,
            patch("process_framework.api.routes.process.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.side_effect = [
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
            ]
            resp = process_client.post("/process/run/sess-default")

        assert resp.status_code == 200
        assert resp.json()["auto_evaluated"] is False
        mock_judge.assert_not_called()

    def test_auto_evaluate_empty_scores_graceful(self, process_client):
        """If the LLM judge returns empty scores, the pipeline still succeeds."""
        with (
            patch(
                "process_framework.api.routes.process.llm_judge_evaluate",
                new=AsyncMock(return_value={}),  # empty — LLM failed to score
            ),
            patch("process_framework.api.routes.process.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.side_effect = [
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
                _make_process_async_client(
                    self._messages(),
                    self._bad_cases(),
                    supabase_insert_ok(),
                ),
            ]
            resp = process_client.post("/process/run/sess-empty?auto_evaluate=true")

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_evaluated"] is False  # no scores → not counted as evaluated

    def test_auto_evaluate_with_bad_case(self, process_client):
        """auto_evaluate works correctly when the session has a flagged bad case."""
        judge_scores = {"factual_grounding": 2, "hallucination_level": 2}
        bad_cases = ok_response(
            [{"message_id": "msg-a1", "category": "factual", "reason": "Wrong date", "ignored_keywords": []}],
            200,
        )
        with (
            patch(
                "process_framework.api.routes.process.llm_judge_evaluate",
                new=AsyncMock(return_value=judge_scores),
            ),
            patch("process_framework.api.routes.process.httpx.AsyncClient") as mock_cls,
        ):
            mock_cls.side_effect = [
                _make_process_async_client(
                    self._messages(),
                    bad_cases,
                    supabase_insert_ok(),
                ),
                _make_process_async_client(
                    self._messages(),
                    bad_cases,
                    supabase_insert_ok(),
                ),
            ]
            resp = process_client.post("/process/run/sess-badcase?auto_evaluate=true")

        assert resp.status_code == 200
        data = resp.json()
        assert data["auto_evaluated"] is True
