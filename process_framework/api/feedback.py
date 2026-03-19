"""
Audit-feedback guard prompt builder for the PROCESS Chat Auditing API.

Before the LLM generates a response it is shown a concise system-level
reminder that summarises every bad case and audit finding recorded for the
current session.  This closes the loop so that audit and bad-case data
actively influences the model's output and helps it avoid repeating known
hallucinations or other failures.

Public surface::

    guard = await build_session_guard(session_id, settings)
    if guard:
        messages = inject_guard_prompt(messages, guard)
"""

from __future__ import annotations

from typing import Dict, List, Optional

import httpx

from process_framework.api.config import Settings

# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

_CATEGORY_LABELS: Dict[str, str] = {
    "hallucination": "HALLUCINATION",
    "intent_understanding": "INTENT / CONSTRAINT MISSED",
    "user_experience": "USER EXPERIENCE",
    "factual": "FACTUAL ERROR",
    "logical": "LOGICAL ERROR",
    "referential": "REFERENTIAL ERROR",
}


def _supa_headers(settings: Settings) -> Dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


async def fetch_session_bad_cases(
    session_id: str,
    settings: Settings,
) -> List[Dict]:
    """
    Return all bad-case records for *session_id* from Supabase.

    Returns an empty list on any network or parsing error so that callers can
    always proceed safely even when Supabase is unavailable.
    """
    url = (
        f"{settings.supabase_url}/rest/v1/bad_cases"
        f"?session_id=eq.{session_id}"
        f"&select=category,reason,ignored_keywords,root_cause,expected_output"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_supa_headers(settings))
            if resp.status_code != 200:
                return []
            return resp.json() or []
    except Exception:  # noqa: BLE001 - degrade gracefully
        return []


# ---------------------------------------------------------------------------
# Guard prompt builder
# ---------------------------------------------------------------------------

_GUARD_HEADER = (
    "[AUDIT FEEDBACK - DO NOT IGNORE]\n"
    "Previous responses in this session were audited and the following issues "
    "were identified. You MUST avoid repeating these failures in your next response:\n"
)

_GUARD_FOOTER = (
    "\nTo prevent hallucinations:\n"
    "1. Only state facts you are confident are accurate.\n"
    "2. Honour every explicit constraint given by the user "
    "(time periods, budgets, style preferences, etc.).\n"
    "3. If you are uncertain, acknowledge it rather than guessing.\n"
    "4. Do not fabricate names, dates, statistics, or citations."
)


def build_guard_prompt(bad_cases: List[Dict]) -> str:
    """
    Convert a list of bad-case records into a concise guard system message.

    Args:
        bad_cases: List of dicts with keys ``category``, ``reason``,
                   ``ignored_keywords``, ``root_cause``, ``expected_output``.

    Returns:
        A non-empty string suitable for use as a system message, or an empty
        string when *bad_cases* is empty.
    """
    if not bad_cases:
        return ""

    lines: List[str] = [_GUARD_HEADER]
    for i, bc in enumerate(bad_cases, start=1):
        category = bc.get("category", "hallucination")
        label = _CATEGORY_LABELS.get(category, category.upper())
        reason = (bc.get("reason") or "").strip()
        root_cause = (bc.get("root_cause") or "").strip()
        expected = (bc.get("expected_output") or "").strip()
        keywords = bc.get("ignored_keywords") or []

        entry = f"{i}. [{label}] {reason}"
        if root_cause:
            entry += f" - Root cause: {root_cause}"
        if expected:
            entry += f" - Expected: {expected}"
        if keywords:
            kw_str = ", ".join(f'"{k}"' for k in keywords)
            entry += f" - Key constraints to honour: {kw_str}"
        lines.append(entry)

    lines.append(_GUARD_FOOTER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Message list injection
# ---------------------------------------------------------------------------


def inject_guard_prompt(
    messages: List[Dict],
    guard_text: str,
) -> List[Dict]:
    """
    Inject *guard_text* into *messages* as a system message.

    * If a system message already exists as the **first** entry it is
      augmented with the guard text appended after a blank line.
    * Otherwise a new system message is prepended.

    The original list is not mutated; a new list is returned.

    Args:
        messages: OpenAI-style message list.
        guard_text: Non-empty guard string produced by :func:`build_guard_prompt`.

    Returns:
        A new message list with the guard injected.
    """
    if not guard_text:
        return messages

    if messages and messages[0].get("role") == "system":
        augmented = dict(messages[0])
        augmented["content"] = messages[0]["content"] + "\n\n" + guard_text
        return [augmented] + list(messages[1:])

    return [{"role": "system", "content": guard_text}] + list(messages)


# ---------------------------------------------------------------------------
# Convenience entry-point used by the chat route
# ---------------------------------------------------------------------------


async def build_session_guard(
    session_id: str,
    settings: Settings,
) -> Optional[str]:
    """
    Fetch bad cases for *session_id* and return a guard prompt string.

    Returns ``None`` when there are no bad cases to report so callers can
    skip injection with a simple ``if guard:`` check.
    """
    bad_cases = await fetch_session_bad_cases(session_id, settings)
    if not bad_cases:
        return None
    return build_guard_prompt(bad_cases) or None
