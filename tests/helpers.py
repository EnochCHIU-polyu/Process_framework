"""Shared test helper utilities for API tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock


def ok_response(body: Any, status_code: int = 201) -> MagicMock:
    """Return a mock httpx.Response with json() → body."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.raise_for_status = MagicMock()
    return resp


def supabase_insert_ok() -> MagicMock:
    return ok_response([], 201)


def supabase_session_ok() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 201
    resp.json.return_value = []
    resp.text = "[]"
    return resp


def supa_async_client(*responses) -> MagicMock:
    """Build a mock httpx.AsyncClient context manager for Supabase calls only."""
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=list(responses))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm
