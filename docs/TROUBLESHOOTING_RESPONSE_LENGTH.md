# 🔧 Troubleshooting: "Flagged Bad Cases Not Working"

## Your Problem

You flagged "response too long" multiple times in the database, but the responses are **still long**.

---

## 🎯 Root Cause Diagnosis

The issue is one of these (in order of likelihood):

| #     | Issue                      | Symptom                                     | Fix                                                         |
| ----- | -------------------------- | ------------------------------------------- | ----------------------------------------------------------- |
| **1** | Session ID not persisting  | Each message = new session                  | Check your chat UI sends `session_id` back                  |
| **2** | Bad cases in wrong session | Flagged in session A, chatting in session B | Use console to verify same `session_id`                     |
| **3** | Supabase connection issue  | Bad cases stored but not retrieved          | Check env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| **4** | Guard not injected         | Bad cases exist but aren't used             | Run diagnostic script                                       |
| **5** | LLM ignores guard          | Guard injected but model doesn't follow it  | Check system prompt is clear                                |

---

## 🚀 Quick Diagnosis (3 Steps)

### Step 1: Check Session ID is Persisting

Open browser console (F12) and run:

```javascript
// Add this to your chat UI to log session IDs
const originalFetch = window.fetch;
window.fetch = function (...args) {
  if (args[0].includes("/chat")) {
    const body = JSON.parse(args[1].body);
    console.log("CHAT REQUEST session_id:", body.session_id);
  }
  return originalFetch.apply(this, args).then((r) => {
    if (args[0].includes("/chat")) {
      return r
        .clone()
        .json()
        .then((data) => {
          console.log("CHAT RESPONSE session_id:", data.session_id);
          return Promise.resolve(new Response(JSON.stringify(data)));
        });
    }
    return r;
  });
};
```

**Expected output:**

```
CHAT REQUEST session_id: null
CHAT RESPONSE session_id: "f47ac10b-..."
CHAT REQUEST session_id: "f47ac10b-..."  ← Should be SAME
CHAT RESPONSE session_id: "f47ac10b-..."
```

❌ **Problem:** If session IDs are different each turn → Chat UI isn't sending `session_id` back

### Step 2: Check Bad Cases in Supabase

```sql
-- In Supabase SQL editor
SELECT session_id, COUNT(*) as bad_case_count,
       array_agg(category) as categories
FROM bad_cases
GROUP BY session_id
ORDER BY COUNT(*) DESC;
```

**Expected output:**

```
session_id              | bad_case_count | categories
f47ac10b-...           | 5              | ["user_experience", "user_experience", ...]
```

❌ **Problem:** If session_id with your flags isn't showing → You flagged in wrong session

### Step 3: Run Diagnostic Script

```bash
source .venv/bin/activate
python diagnose_learning_loop.py
```

This will:

- ✓ Create a new chat session
- ✓ Send a turn
- ✓ Query bad cases in Supabase
- ✓ Build session guard
- ✓ Test guard injection
- ✓ Show where the issue is

---

## 🔍 Common Issues & Fixes

### Issue #1: "Chat UI Doesn't Send Session ID Back"

**Symptom:** Every message creates a new session (session IDs in console are all different)

**Fix:** Make sure chat UI code has:

```javascript
let sessionId = null;

async function sendMessage() {
  // ... existing code ...
  const res = await fetch("/chat", {
    body: JSON.stringify({
      session_id: sessionId, // ← This line is critical
      messages: history,
    }),
  });

  const data = await res.json();
  sessionId = data.session_id; // ← Save it for next time
}
```

**Check:** Does your `chat_ui.html` have this? (Should be around line 310)

---

### Issue #2: "Bad Cases Exist But Guard Isn't Built"

**Symptom:** Query shows bad cases in Supabase, but responses aren't getting shorter

**Fix:** Verify environment variables are set:

```bash
echo $SUPABASE_URL
echo $SUPABASE_SERVICE_ROLE_KEY
```

Both should have values. If empty:

```bash
# Add to .env
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="eyJ..."
```

Then restart server:

```bash
pkill uvicorn
uvicorn process_framework.api.main:app --reload
```

---

### Issue #3: "Guard Built But Model Doesn't Follow It"

**Symptom:** Guard is injected (you see it in logs) but model ignores it

**Fix:** The guard might not be strong enough. Check in `process_framework/api/feedback.py`:

```python
_GUARD_HEADER = """\
⚠️ AUDIT FINDINGS FROM THIS SESSION - APPLY THESE CORRECTIONS:
"""
```

Make it more direct:

```python
_GUARD_HEADER = """\
🚨 CRITICAL: Apply these rules or your response will be wrong:

"""
```

---

### Issue #4: "Session ID is Null Every Turn"

**Symptom:** Console shows `session_id: null` on every single request

**Fix 1:** The chat UI should initialize a session on the first message. Check that this code runs:

```javascript
let sessionId = null; // ← Should exist at top of script

// After first chat response:
const data = await res.json();
sessionId = data.session_id; // ← This should set it
```

**Fix 2:** If even Turn 1 doesn't return a session_id, the backend might be broken:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": null,
    "messages": [{"role": "user", "content": "test"}]
  }' | jq .session_id
```

Should return a UUID. If null → Backend issue.

---

## 🧪 Full Diagnostic Flowchart

```
❓ Responses still long even after flagging

├─ Check: Is session_id SAME every turn?
│  ├─ NO  → Fix: Chat UI not sending session_id back
│  │        Solution: Add sessionId = data.session_id after each response
│  │
│  └─ YES → Continue...

├─ Check: Do bad_cases exist in Supabase for that session?
│  ├─ NO  → Issue: Bad cases not being saved
│  │        Debug: Check /flag endpoint is being called
│  │
│  └─ YES → Continue...

├─ Check: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY set?
│  ├─ NO  → Fix: Add to .env and restart server
│  │
│  └─ YES → Continue...

├─ Run: python diagnose_learning_loop.py
│  ├─ Guard NOT BUILT → SUPABASE credentials wrong
│  ├─ Guard BUILT but model doesn't follow → Make guard prompt stronger
│  └─ Everything OK but still broken → Model/LLM issue
```

---

## 🧑‍💻 Manual Testing (No UI Needed)

```bash
# Terminal 1: Start server with debug logging
RUST_LOG=debug uvicorn process_framework.api.main:app --reload

# Terminal 2: Manually test the flow
python3 << 'EOF'
import asyncio, httpx, json

API = "http://localhost:8000"

async def test():
    # Turn 1: Get session
    r1 = await httpx.AsyncClient().post(f"{API}/chat", json={
        "session_id": None,
        "messages": [{"role": "user", "content": "Write a VERY long response"}]
    })
    sid = r1.json()["session_id"]
    print(f"Session: {sid}")
    print(f"Response length: {len(r1.json()['assistant_message'])}")

    # Flag it
    await httpx.AsyncClient().post(f"{API}/audit/{sid}/flag-hallucination", json={
        "reason": "Response too long",
        "category": "user_experience"
    })
    print("Flagged as bad case")

    # Turn 2: See if guard works
    r2 = await httpx.AsyncClient().post(f"{API}/chat", json={
        "session_id": sid,
        "messages": [{"role": "user", "content": "Write a SHORT response"}]
    })
    print(f"Response length after flag: {len(r2.json()['assistant_message'])}")

asyncio.run(test())
EOF
```

---

## ✅ How to Know It's Fixed

When working correctly:

1. **Same session ID** every turn ✓
2. **Bad cases in Supabase** for that session ✓
3. **Session guard builds** with your fixes ✓
4. **Guard in system prompt** before model response ✓
5. **Model follows guard** → shorter/better responses ✓

---

## 📞 Still Stuck?

Run the full diagnostic:

```bash
python diagnose_learning_loop.py
```

This outputs:

- ✅ Session ID persistence status
- ✅ Bad cases retrieved from DB
- ✅ Session guard built
- ✅ Response length with guard active

Share the output and we can pinpoint the exact issue!

---

## 🎯 TL;DR

**Most likely fix:** Your chat UI needs this line:

```javascript
const data = await res.json();
sessionId = data.session_id; // ← Add this after every response
```

Without it, each message gets a new session, so the flagged bad cases from the previous session aren't used.

Check `chat_ui.html` around line 310 — is this line there?
