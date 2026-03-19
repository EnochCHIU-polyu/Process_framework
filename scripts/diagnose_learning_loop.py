#!/usr/bin/env python3
"""
Diagnostic script to verify bad case learning loop is working correctly.

This checks:
1. Session ID is being persisted
2. Bad cases are stored in Supabase
3. Session guard is being built
4. Response length is being tracked
"""

import asyncio
import json
from typing import Optional

import httpx

from process_framework.api.config import Settings


async def test_session_persistence():
    """
    Test that session_id persists across chat turns.
    
    Expected:
    1. Turn 1: session_id=None → returns session_id="abc123"
    2. Turn 2: session_id="abc123" → uses same session
    3. Turn 3: session_id="abc123" → guard should be active
    """
    print("\n" + "=" * 70)
    print("TEST 1: Session ID Persistence")
    print("=" * 70)

    settings = Settings()
    api_base = "http://localhost:8000"
    session_id: Optional[str] = None

    # Turn 1
    print("\n▶ Turn 1: Sending first message (no session_id yet)")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{api_base}/chat",
            json={
                "session_id": None,
                "messages": [
                    {
                        "role": "user",
                        "content": "What is the capital of France? Give a long detailed answer with history.",
                    }
                ],
                "temperature": 0.7,
            },
        )

        if resp.status_code != 200:
            print(f"❌ Error: {resp.status_code} - {resp.text}")
            return

        data = resp.json()
        session_id = data.get("session_id")
        msg_1 = data.get("assistant_message")

        print(f"✓ Session ID received: {session_id}")
        print(f"✓ Response length: {len(msg_1)} chars")
        print(f"✓ Response preview: {msg_1[:80]}...")

    # Turn 2: Send with session_id
    print("\n▶ Turn 2: Sending second message (WITH session_id)")
    print(f"  Using session_id: {session_id}")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{api_base}/chat",
            json={
                "session_id": session_id,  # ← SAME SESSION
                "messages": [
                    {
                        "role": "user",
                        "content": "What is the capital of France? Give a long detailed answer with history.",
                    },
                    {"role": "assistant", "content": msg_1},
                    {
                        "role": "user",
                        "content": "Can you verify your answer? How sure are you?",
                    },
                ],
                "temperature": 0.7,
            },
        )

        if resp.status_code != 200:
            print(f"❌ Error: {resp.status_code} - {resp.text}")
            return

        data = resp.json()
        returned_session = data.get("session_id")
        msg_2 = data.get("assistant_message")

        print(f"✓ Session ID matches: {returned_session == session_id}")
        print(f"✓ Response length: {len(msg_2)} chars")
        print(f"✓ Response preview: {msg_2[:80]}...")

    print("\n✅ Session persistence test complete")
    return session_id


async def test_bad_case_storage(session_id: str):
    """
    Check if bad cases are being stored in Supabase.
    """
    print("\n" + "=" * 70)
    print("TEST 2: Bad Case Storage in Supabase")
    print("=" * 70)

    settings = Settings()
    api_base = "http://localhost:8000"

    print(f"\n▶ Querying bad_cases for session: {session_id}")

    async with httpx.AsyncClient(timeout=30) as client:
        url = (
            f"{settings.supabase_url}/rest/v1/bad_cases"
            f"?session_id=eq.{session_id}"
        )
        headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }

        resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            print(f"❌ Error querying Supabase: {resp.status_code}")
            print(f"   Make sure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set")
            return []

        bad_cases = resp.json()
        print(f"✓ Found {len(bad_cases)} bad cases in Supabase")

        for i, bc in enumerate(bad_cases, 1):
            print(f"\n  Bad Case #{i}:")
            print(f"    Category: {bc.get('category')}")
            print(f"    Reason: {bc.get('reason', 'N/A')[:60]}...")
            print(f"    Keywords: {bc.get('ignored_keywords', [])}")

        return bad_cases


async def test_session_guard_build(session_id: str, bad_cases: list):
    """
    Test that session guard is built from bad cases.
    """
    print("\n" + "=" * 70)
    print("TEST 3: Session Guard Generation")
    print("=" * 70)

    if not bad_cases:
        print("\n⚠️  No bad cases found. Skipping session guard test.")
        print("   (Flag a bad case first to test guard injection)")
        return

    settings = Settings()
    api_base = "http://localhost:8000"

    print(f"\n▶ Building session guard for: {session_id}")

    # Import the feedback module to call guard builder directly
    from process_framework.api.feedback import build_session_guard

    guard = await build_session_guard(session_id, settings)

    if not guard:
        print("❌ Session guard is empty (no bad cases retrieved)")
        return

    print("✓ Session guard built successfully:")
    print("\n" + "─" * 70)
    print(guard)
    print("─" * 70)


async def test_chat_with_guard(session_id: str):
    """
    Send a new message and verify guard is injected.
    """
    print("\n" + "=" * 70)
    print("TEST 4: Chat With Guard Injection")
    print("=" * 70)

    api_base = "http://localhost:8000"

    print(f"\n▶ Sending message with session guard (session: {session_id})")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{api_base}/chat",
            json={
                "session_id": session_id,
                "messages": [
                    {
                        "role": "user",
                        "content": "Now give me a SHORT answer about France's capital.",
                    }
                ],
                "temperature": 0.7,
            },
        )

        if resp.status_code != 200:
            print(f"❌ Error: {resp.status_code} - {resp.text}")
            return

        data = resp.json()
        msg = data.get("assistant_message")

        print(f"✓ Response received")
        print(f"✓ Response length: {len(msg)} chars")
        print(f"\n  Response:\n  {msg}")

        if len(msg) < 200:
            print(f"\n✅ Response is short! Guard likely injected.")
        else:
            print(
                f"\n⚠️  Response is still long ({len(msg)} chars)."
            )
            print(
                "   This might mean the guard wasn't injected."
            )


async def main():
    """Run all diagnostic tests."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║         Bad Case Learning Loop - Diagnostic Tests                   ║
║                                                                      ║
║ This script tests the full feedback loop to diagnose why flagged    ║
║ bad cases aren't working correctly.                                 ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    try:
        # Test 1: Session persistence
        session_id = await test_session_persistence()
        if not session_id:
            print("❌ Failed to get session_id. Aborting remaining tests.")
            return

        # Test 2: Bad case storage
        bad_cases = await test_bad_case_storage(session_id)

        # Test 3: Guard building
        await test_session_guard_build(session_id, bad_cases)

        # Test 4: Chat with guard
        await test_chat_with_guard(session_id)

    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 70)
    print("Diagnostic tests complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
