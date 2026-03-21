#!/usr/bin/env python3
"""
Diagnostic tool to understand why LLM is not learning from bad_cases.

Usage:
    python scripts/diagnose_guard_injection.py <session_id>

This will:
1. Fetch all bad cases for the session
2. Fetch all learned patterns from DB
3. Show the guard prompt that would be built
4. Explain why LLM might not be learning
"""

import asyncio
import sys
from typing import Optional

import httpx

from process_framework.api.config import Settings
from process_framework.api.feedback import (
    build_guard_prompt,
    build_session_guard,
    fetch_learned_patterns,
    fetch_session_bad_cases,
    fetch_global_bad_cases,
)


def _supa_headers(settings: Settings) -> dict:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


async def fetch_session_messages(session_id: str, settings: Settings) -> list:
    """Fetch all messages in the session to understand context."""
    url = (
        f"{settings.supabase_url}/rest/v1/chat_messages"
        f"?session_id=eq.{session_id}&order=created_at.asc"
        f"&select=id,role,content,created_at"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_supa_headers(settings))
            if resp.status_code == 200:
                return resp.json() or []
    except Exception as e:
        print(f"❌ Failed to fetch messages: {e}")
    return []


async def fetch_session_audits(session_id: str, settings: Settings) -> list:
    """Fetch all audits for the session to see what was triaged."""
    url = (
        f"{settings.supabase_url}/rest/v1/ai_audits"
        f"?session_id=eq.{session_id}&order=created_at.desc"
        f"&select=id,message_id,status,verdict,analysis_label,analysis_summary,bad_case_id"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=_supa_headers(settings))
            if resp.status_code == 200:
                return resp.json() or []
    except Exception as e:
        print(f"❌ Failed to fetch audits: {e}")
    return []


async def main(session_id: str):
    """Run diagnostics on why LLM is not learning from bad_cases."""
    settings = Settings()
    
    print(f"\n{'=' * 80}")
    print(f"LEARNING LOOP DIAGNOSTIC — Session: {session_id}")
    print(f"{'=' * 80}\n")

    # Step 1: Fetch bad cases
    print("[1] FETCHING SESSION-SPECIFIC BAD CASES...")
    bad_cases = await fetch_session_bad_cases(session_id, settings)
    print(f"✓ Found {len(bad_cases)} session-specific bad case(s)")
    if bad_cases:
        print("\n  SESSION-SPECIFIC BAD CASES:")
        for i, bc in enumerate(bad_cases, 1):
            print(f"\n    #{i}:")
            print(f"      - Category: {bc.get('category')}")
            print(f"      - Reason: {bc.get('reason')}")
            print(f"      - Expected: {(bc.get('expected_output') or '')[:80]}")
            print(f"      - Keywords: {bc.get('ignored_keywords', [])}")
    
    print("\n[1b] FETCHING GLOBAL BAD CASES (from all sessions)...")
    global_bad_cases = await fetch_global_bad_cases(settings, limit=15)
    print(f"✓ Found {len(global_bad_cases)} recent global bad case(s)")
    if global_bad_cases:
        print("\n  GLOBAL BAD CASES (applicable to ALL chats):")
        for i, bc in enumerate(global_bad_cases[:5], 1):
            session_label = f" [Session: {bc.get('session_id', '?')[:8]}...]" if bc.get('session_id') else " [Global]"
            print(f"\n    #{i}{session_label}:")
            print(f"      - Category: {bc.get('category')}")
            print(f"      - Reason: {bc.get('reason')}")
            print(f"      - Expected: {(bc.get('expected_output') or '')[:80]}")
            print(f"      - Keywords: {bc.get('ignored_keywords', [])}")
    else:
        print("  ⚠️  NO GLOBAL BAD CASES FOUND!")
        print("  ➜ Once you flag corrections, they'll appear here and apply to ALL chats.")
    
    # Combine for guard building (what LLM actually sees)
    all_bad_cases = bad_cases.copy()
    session_ids_seen = {bc.get("session_id") for bc in bad_cases}
    for gbc in global_bad_cases:
        if gbc.get("session_id") not in session_ids_seen:
            all_bad_cases.append(gbc)
            session_ids_seen.add(gbc.get("session_id"))

    # Step 2: Fetch learned patterns
    print("\n[2] FETCHING LEARNED PATTERNS FROM DATABASE...")
    learned_patterns = await fetch_learned_patterns(None, settings)
    print(f"✓ Found {len(learned_patterns)} learned pattern cluster(s)")
    if learned_patterns:
        for i, lp in enumerate(learned_patterns[:5], 1):
            print(f"\n  Pattern #{i}:")
            print(f"    - Category: {lp.get('category')}")
            print(f"    - Description: {(lp.get('pattern_description') or '')[:100]}")
            print(f"    - Occurrences: {lp.get('occurrence_count', 1)}")
            print(f"    - Keywords: {lp.get('pattern_keywords', [])}")

    # Step 3: Build the guard prompt
    print("\n[3] BUILDING GUARD PROMPT (with combined session + global bad cases)...")
    print(f"   Total bad cases to use: {len(all_bad_cases)}")
    guard = build_guard_prompt(all_bad_cases, learned_patterns)
    if guard and guard.strip():
        print("✓ Guard prompt built successfully")
        print("\n" + "=" * 80)
        print("GUARD PROMPT (this is injected as system message to LLM):")
        print("=" * 80)
        print(guard)
        print("=" * 80)
    else:
        print("❌ GUARD PROMPT IS EMPTY!")
        print("   ➜ This means LLM gets no guidance from bad cases.")

    # Step 4: Show messages in session
    print("\n[4] CHAT HISTORY IN SESSION...")
    messages = await fetch_session_messages(session_id, settings)
    print(f"✓ Found {len(messages)} message(s)")
    for i, msg in enumerate(messages, 1):
        role_label = "USER" if msg["role"] == "user" else "ASST" if msg["role"] == "assistant" else "SYS"
        content_preview = (msg["content"][:70] + "...") if len(msg["content"]) > 70 else msg["content"]
        print(f"  #{i} [{role_label}] {content_preview}")

    # Step 5: Show audits & triage results
    print("\n[5] AUDIT RESULTS & TRIAGE IN SESSION...")
    audits = await fetch_session_audits(session_id, settings)
    print(f"✓ Found {len(audits)} audit record(s)")
    for i, audit in enumerate(audits, 1):
        label = audit.get("analysis_label", "?")
        verdict = audit.get("verdict", "?")
        status = audit.get("status", "?")
        summary = (audit.get("analysis_summary") or "")[:60]
        print(f"  #{i} - Status: {status}, Verdict: {verdict}, Label: {label}")
        if summary:
            print(f"        Summary: {summary}")

    # Step 6: Diagnostics & recommendations
    print("\n[6] DIAGNOSTICS & RECOMMENDATIONS...")
    print(f"    Sessions-specific bad cases: {len(bad_cases)}")
    print(f"    Global bad cases (from other chats): {len(global_bad_cases)}")
    print(f"    Total combined: {len(all_bad_cases)}")
    print()
    
    if not all_bad_cases:
        print("❌ ISSUE: No bad cases (session + global)!")
        print("   WHY: No corrections have been flagged yet.")
        print("   FIX:")
        print("    1. Start a chat with the user")
        print("    2. When LLM gives wrong answer, provide correction with clear feedback")
        print("    3. Example: 'Wrong! Enoch CHIU is [correct details]'")
        print("    4. Return to this diagnostic to see the bad case appear")

    elif not guard or not guard.strip():
        print("❌ ISSUE: Guard prompt is empty even though bad cases exist!")
        print("   WHY: build_guard_prompt() is returning empty string.")
        print("   FIX:")
        print("    1. Check that bad_cases have required fields (reason, category, etc)")
        print("    2. Restart the API server")

    else:
        print("✓ SETUP LOOKS CORRECT:")
        print("   ✓ Session-specific bad cases loaded (apply only in this chat)")
        print("   ✓ Global bad cases loaded (apply to ALL chats/sessions)")
        print("   ✓ Guard prompt is being built")
        print("   ✓ Guard will be injected into next LLM call")
        print()
        print("   MEANING:")
        print("   - When user sends NEXT message, this guard prompt will be prepended")
        print("   - All corrections flagged (in this or other sessions) will guide LLM")
        print("   - LLM should now apply learned corrections across ALL topics")
        print()
        print("   IF LLM STILL DOESN'T KNOW ABOUT 'ENOCH CHIU':")
        print("   - Temperature might be too high (LLM ignores guidance)")
        print("   - Make expected_output very specific, not generic")
        print("   - Restart API server to reload learned patterns cache")
        print("   - Check if original bad case was saved (see fields above)")

    print(f"\n{'=' * 80}")
    print("END DIAGNOSTIC")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_guard_injection.py <session_id>")
        print("Example: python scripts/diagnose_guard_injection.py 550e8400-e29b-41d4-a716-446655440000")
        sys.exit(1)

    session_id = sys.argv[1]
    asyncio.run(main(session_id))
