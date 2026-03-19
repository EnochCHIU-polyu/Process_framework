"""
Audit-feedback guard prompt builder for the PROCESS Chat Auditing API.

Before the LLM generates a response it is shown a concise system-level
reminder that summarises every bad case and audit finding recorded for the
current session.  This closes the loop so that audit and bad-case data
actively influences the model's output and helps it avoid repeating known
hallucinations or other failures.

Now with clustering: Bad cases are deduplicated and clustered into learned
patterns stored in the database, avoiding repetition and building knowledge
over time and across sessions.

Public surface::

    guard = await build_session_guard(session_id, settings)
    if guard:
        messages = inject_guard_prompt(messages, guard)
"""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

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

_CATEGORY_REMEDIATIONS: Dict[str, str] = {
    "hallucination": "Use only verifiable facts; explicitly say uncertain when confidence is low.",
    "intent_understanding": "Mirror user constraints before answering and ensure every explicit constraint is satisfied.",
    "user_experience": "Prefer concise, direct format; avoid long introductions and repetitive wording.",
    "factual": "Prioritize concrete, non-speculative statements and avoid unsupported details.",
    "logical": "Keep reasoning coherent and consistent; avoid contradictory claims.",
    "referential": "Resolve references clearly (names, entities, pronouns) before producing recommendations.",
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
        f"&order=created_at.desc"
        f"&select=category,reason,ignored_keywords,root_cause,expected_output,actual_output,created_at"
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

_BREVITY_REASON_HINTS = (
    "too long",
    "long response",
    "verbose",
    "wordy",
    "lengthy",
    "冗長",
    "冗长",
    "太長",
    "太长",
    "過長",
    "过长",
)


def _contains_brevity_signal(text: str) -> bool:
    low = text.lower()
    return any(hint in low for hint in _BREVITY_REASON_HINTS)


def _brevity_required(bad_cases: List[Dict]) -> bool:
    for bc in bad_cases:
        reason = (bc.get("reason") or "").strip()
        expected = (bc.get("expected_output") or "").strip()
        keywords = bc.get("ignored_keywords") or []
        if _contains_brevity_signal(reason) or _contains_brevity_signal(expected):
            return True
        if any(_contains_brevity_signal(str(k)) for k in keywords):
            return True
    return False


def _clip(text: str, max_len: int = 160) -> str:
    value = text.strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Clustering helpers — deduplicate and group similar bad cases
# ---------------------------------------------------------------------------


def _keyword_overlap(kw_set1: set[str], kw_set2: set[str]) -> float:
    """
    Calculate Jaccard similarity between two keyword sets.
    Returns float in [0, 1] where 1.0 is identical, 0.0 is disjoint.
    """
    if not kw_set1 and not kw_set2:
        return 1.0
    if not kw_set1 or not kw_set2:
        return 0.0
    intersection = len(kw_set1 & kw_set2)
    union = len(kw_set1 | kw_set2)
    return intersection / union if union > 0 else 0.0


def _string_similarity(s1: str, s2: str) -> float:
    """Calculate string similarity using SequenceMatcher ratio."""
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def _normalize_keywords(keywords: list[str]) -> set[str]:
    """Extract and normalize keywords to lowercase, deduped set."""
    normalized = set()
    for kw in keywords:
        kw_text = str(kw).strip().lower()
        if kw_text and len(kw_text) > 2:  # Skip short noise
            normalized.add(kw_text)
    return normalized


def _cluster_bad_cases(bad_cases: List[Dict]) -> List[Dict]:
    """
    Cluster bad cases by semantic similarity.

    Groups cases by:
    1. Category (primary grouping)
    2. Keyword overlap (secondary grouping within category)
    3. Reason text similarity (tertiary grouping)

    Returns list of cluster dicts with:
        - cluster_id: unique identifier
        - category: bad case category
        - pattern_keywords: deduplicated keywords from cluster
        - pattern_description: normalized summary of reason/root_cause
        - remediation_guidance: guidance for this cluster
        - occurrence_count: how many bad cases in this cluster
        - cases: original bad_cases in cluster
    """
    if not bad_cases:
        return []

    clusters: List[Dict] = []

    for bc in bad_cases:
        category = (bc.get("category") or "hallucination").strip()
        keywords = _normalize_keywords(bc.get("ignored_keywords") or [])
        reason = (bc.get("reason") or "").strip()
        root_cause = (bc.get("root_cause") or "").strip()

        # Try to find existing cluster with high similarity
        matched_cluster_idx = -1
        best_similarity = 0.0

        for idx, cluster in enumerate(clusters):
            if cluster["category"] != category:
                continue

            # Check keyword overlap
            cluster_kw = set(cluster["pattern_keywords"])
            kw_sim = _keyword_overlap(keywords, cluster_kw)

            # Check reason similarity
            reason_sim = _string_similarity(reason, cluster.get("_reason_sample", ""))

            # Combined similarity (prefer keyword match)
            combined_sim = 0.7 * kw_sim + 0.3 * reason_sim
            if combined_sim > best_similarity:
                best_similarity = combined_sim
                matched_cluster_idx = idx

        # If found matching cluster with >60% similarity, add to it
        if matched_cluster_idx >= 0 and best_similarity > 0.6:
            clusters[matched_cluster_idx]["occurrence_count"] += 1
            clusters[matched_cluster_idx]["cases"].append(bc)
            # Merge keywords
            clusters[matched_cluster_idx]["pattern_keywords"] = list(
                set(clusters[matched_cluster_idx]["pattern_keywords"]) | keywords
            )
        else:
            # Create new cluster
            clusters.append({
                "cluster_id": f"{category}_{len(clusters)}",
                "category": category,
                "pattern_keywords": list(keywords),
                "_reason_sample": reason,
                "pattern_description": _clip(reason or root_cause or "Unnamed issue", 120),
                "remediation_guidance": _CATEGORY_REMEDIATIONS.get(
                    category,
                    "Resolve the issue explicitly before finalizing the answer."
                ),
                "occurrence_count": 1,
                "cases": [bc],
            })

    return clusters


async def fetch_learned_patterns(
    category: Optional[str],
    settings: Settings,
) -> List[Dict]:
    """
    Fetch learned patterns from database, optionally filtered by category.

    Returns empty list on any error so callers can proceed safely.
    """
    url = f"{settings.supabase_url}/rest/v1/learned_patterns"
    query_parts = ["order=occurrence_count.desc", "limit=50"]
    if category:
        query_parts.append(f"category=eq.{category}")
    url_with_query = f"{url}?{'&'.join(query_parts)}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url_with_query, headers=_supa_headers(settings))
            if resp.status_code == 200:
                return resp.json() or []
            return []
    except Exception:  # noqa: BLE001
        return []


async def upsert_pattern_cluster(
    cluster: Dict,
    settings: Settings,
) -> None:
    """
    Store or update a pattern cluster in the learned_patterns table.

    If a pattern with the same category + keywords already exists,
    increment occurrence_count and update last_seen.
    Otherwise create a new pattern.
    """
    category = cluster.get("category", "user_experience")
    keywords = cluster.get("pattern_keywords", [])
    description = cluster.get("pattern_description", "")
    remediation = cluster.get("remediation_guidance", "")

    # Try to find existing pattern with exact keyword overlap
    # For simplicity, we'll create new pattern each time with incremented count
    # (In production, you might use a hash of keywords to check for duplicates)
    url = f"{settings.supabase_url}/rest/v1/learned_patterns"

    payload = {
        "category": category,
        "pattern_keywords": keywords,
        "pattern_description": description,
        "remediation_guidance": remediation,
        "occurrence_count": cluster.get("occurrence_count", 1),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers=_supa_headers(settings),
            )
            # Success if 201 (created) or 200 (ok)
            return resp.status_code in (200, 201)
    except Exception:  # noqa: BLE001
        pass  # Fail gracefully; it's ok if we can't store


def _build_prompt_policy(
    bad_cases: List[Dict],
    learned_patterns: List[Dict],
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """
    Build an adaptive policy from bad cases and learned patterns.

    Combines fresh bad cases (this session) with accumulated learned patterns
    (from DB across all sessions) to create comprehensive guidance.

    Returns:
        - optimization_rules: Core behavior rules
        - high_priority_constraints: Frequent constraints/keywords
        - learned_corrections: Example corrections
        - scrutiny_checklist: Final self-check items
    """
    category_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()

    learned_corrections: List[str] = []
    seen_corrections: set[str] = set()

    # Count from fresh bad cases
    for bc in bad_cases:
        category = (bc.get("category") or "hallucination").strip()
        category_counter[category] += 1

        reason = (bc.get("reason") or "").strip()
        if reason:
            reason_counter[_clip(reason, 120)] += 1

        keywords = bc.get("ignored_keywords") or []
        for kw in keywords:
            kw_text = str(kw).strip()
            if kw_text:
                keyword_counter[kw_text] += 1

        actual = (bc.get("actual_output") or "").strip()
        expected = (bc.get("expected_output") or "").strip()
        if expected and expected not in seen_corrections:
            seen_corrections.add(expected)
            if actual:
                learned_corrections.append(
                    f"Avoid pattern: '{_clip(actual, 90)}' -> Prefer: '{_clip(expected, 120)}'"
                )
            else:
                learned_corrections.append(f"Preferred style: '{_clip(expected, 120)}'")

    # Weight learned patterns (accumulated across sessions)
    for pattern in learned_patterns[:10]:  # Top 10 most frequent patterns
        category = (pattern.get("category") or "hallucination").strip()
        # Add weight from learned patterns (but less than fresh cases)
        category_counter[category] += max(1, pattern.get("occurrence_count", 1) // 3)

        keywords = pattern.get("pattern_keywords") or []
        for kw in keywords:
            kw_text = str(kw).strip()
            if kw_text:
                keyword_counter[kw_text] += 2  # Boost keywords from learned patterns

    optimization_rules: List[str] = []
    for category, count in category_counter.most_common(4):
        label = _CATEGORY_LABELS.get(category, category.upper())
        remediation = _CATEGORY_REMEDIATIONS.get(
            category,
            "Resolve the issue explicitly before finalizing the answer.",
        )
        optimization_rules.append(f"[{label}] x{count}: {remediation}")

    if not optimization_rules:
        optimization_rules.append(
            "Use accurate, constraint-aware, concise responses and avoid repeating known failures."
        )

    high_priority_constraints: List[str] = []
    for kw, count in keyword_counter.most_common(8):
        priority = "HIGH" if count >= 3 else "NORMAL"
        high_priority_constraints.append(f"{kw} (priority={priority}, seen={count})")

    for reason, count in reason_counter.most_common(3):
        if count >= 2:
            high_priority_constraints.append(
                f"Repeated issue x{count}: {reason}"
            )

    scrutiny_checklist: List[str] = [
        "Did I satisfy all user constraints and keywords?",
        "Did I remove any unsupported / speculative claims?",
        "Is the answer concise and directly actionable?",
        "Did I avoid repeating previously flagged failure patterns?",
    ]

    return optimization_rules, high_priority_constraints, learned_corrections[:3], scrutiny_checklist


def build_guard_prompt(
    bad_cases: List[Dict],
    learned_patterns: Optional[List[Dict]] = None,
) -> str:
    """
    Convert bad cases and learned patterns into a concise guard system message.

    Args:
        bad_cases: List of dicts with keys ``category``, ``reason``,
                   ``ignored_keywords``, ``root_cause``, ``expected_output``.
        learned_patterns: Optional list of dicts from learned_patterns table
                         (cached patterns from previous sessions).

    Returns:
        A non-empty string suitable for use as a system message, or an empty
        string when both are empty.
    """
    if not bad_cases and not learned_patterns:
        return ""

    learned_patterns = learned_patterns or []

    optimization_rules, high_priority_constraints, learned_corrections, scrutiny_checklist = (
        _build_prompt_policy(bad_cases, learned_patterns)
    )

    lines: List[str] = [_GUARD_HEADER]
    lines.append("[PROCESS-LOOP POLICY SNAPSHOT]")

    # Show both fresh and learned counts
    fresh_count = len(bad_cases)
    learned_count = len(learned_patterns)
    lines.append(f"- Fresh issues (this session): {fresh_count}")
    if learned_count > 0:
        total_learned = sum(p.get("occurrence_count", 1) for p in learned_patterns[:5])
        lines.append(f"- Learned patterns (accumulated): {learned_count} clusters (μ {total_learned} occurrences)")

    lines.append("")
    lines.append("[P/O - PURPOSE & OPTIMIZATION RULES]")
    for rule in optimization_rules:
        lines.append(f"- {rule}")

    if high_priority_constraints:
        lines.append("")
        lines.append("[R/C - HIGH PRIORITY CONSTRAINTS]")
        for item in high_priority_constraints:
            lines.append(f"- {item}")

    if learned_corrections:
        lines.append("")
        lines.append("[LEARNED CORRECTION PATTERNS]")
        for item in learned_corrections:
            lines.append(f"- {item}")

    if _brevity_required(bad_cases):
        lines.extend(
            [
                "",
                "[MANDATORY RESPONSE CONTRACT]",
                "BREVITY_MODE=ON",
                "- Keep the final answer concise and practical.",
                "- Maximum 4 bullet points OR 4 short sentences.",
                "- No long preface, no repeated explanation, no extra sections.",
                "- If user asks for more detail, then expand in follow-up.",
            ]
        )

    lines.append("")
    lines.append("[S/S - SELF SCRUTINY CHECKLIST BEFORE RESPONDING]")
    for item in scrutiny_checklist:
        lines.append(f"- {item}")

    lines.append(_GUARD_FOOTER)
    return "\n".join(lines)

    if learned_corrections:
        lines.append("")
        lines.append("[LEARNED CORRECTION PATTERNS]")
        for item in learned_corrections:
            lines.append(f"- {item}")

    if _brevity_required(bad_cases):
        lines.extend(
            [
                "",
                "[MANDATORY RESPONSE CONTRACT]",
                "BREVITY_MODE=ON",
                "- Keep the final answer concise and practical.",
                "- Maximum 4 bullet points OR 4 short sentences.",
                "- No long preface, no repeated explanation, no extra sections.",
                "- If user asks for more detail, then expand in follow-up.",
            ]
        )

    lines.append("")
    lines.append("[S/S - SELF SCRUTINY CHECKLIST BEFORE RESPONDING]")
    for item in scrutiny_checklist:
        lines.append(f"- {item}")

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
      augmented with the guard text prepended before a blank line so learned
      policy has highest instruction priority.
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
        augmented["content"] = guard_text + "\n\n" + messages[0]["content"]
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
    Fetch bad cases for *session_id*, cluster them, store in DB, fetch learned
    patterns, and return a guard prompt string.

    Flow:
    1. Fetch all bad cases for this session
    2. Cluster bad cases to deduplicate similar meanings
    3. Store non-duplicate clusters in learned_patterns table
    4. Fetch top learned patterns from DB (accumulated across sessions)
    5. Build guard from fresh clusters + accumulated patterns

    Returns ``None`` when there are no bad cases and no learned patterns
    to report so callers can skip injection with a simple ``if guard:`` check.
    """
    bad_cases = await fetch_session_bad_cases(session_id, settings)

    # Cluster bad cases to deduplicate similar meanings
    clusters = _cluster_bad_cases(bad_cases)

    # For each cluster, store in learned_patterns table
    for cluster in clusters:
        await upsert_pattern_cluster(cluster, settings)

    # Fetch accumulated learned patterns from DB
    # Get top patterns across all categories
    learned_patterns = await fetch_learned_patterns(None, settings)

    # Build guard from fresh clusters + learned patterns
    guard_text = build_guard_prompt(bad_cases, learned_patterns)

    return guard_text if guard_text.strip() else None
