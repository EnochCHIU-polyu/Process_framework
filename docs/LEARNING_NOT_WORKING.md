# Why LLM is Not Learning from Bad Cases — Diagnostic Guide

## Problem Statement

You flagged a bad case about "Enoch CHIU" but the LLM doesn't know the answer on the next turn.

## Root Causes (in order of likelihood)

### 1. ⚠️ **Bad case wasn't actually saved** (Most common)

When you flag a correction in the chat UI, the system should:

1. Detect user dissatisfaction (uses sentiment analysis)
2. Extract the correction (uses LLM)
3. **Triage** it as `bad_case` OR `preference` OR `unclear`
4. **Only if triage = `bad_case`**: save to database

**If result wasn't saved**: triage likely classified it as `preference` or `unclear`.

### Solution 1A: Check the triage classification

```bash
# In Supabase SQL Editor:
SELECT id, verdict, analysis_label, analysis_summary FROM ai_audits
  ORDER BY created_at DESC LIMIT 5;
```

Look for:

- `analysis_label = "bad_case"` → Correction should be in bad_cases table
- `analysis_label = "preference"` → System thinks you wanted formatting, not correction
- `analysis_label = "unclear"` → Not enough confidence, needs manual review

### Solution 1B: Make feedback more explicit

The triage LLM needs clear signals:

❌ **Too vague:**

- "That's not right"
- "Wrong"
- "Can you fix this?"

✅ **Clear bad_case signal:**

- "Wrong, Enoch CHIU is [specific bio]. You said [what was wrong]."
- "Factually incorrect: Enoch CHIU didn't [action]. The correct fact is ..."
- "Hallucination detected: You made up that Enoch CHIU [false claim]."

✅ **Preference signal (won't create bad_case):**

- "Can you make this shorter?"
- "Use bullet points instead"
- "More casual tone please"

---

### 2. ⚠️ **Bad case saved but guard not being fetched** (Session ID mismatch)

Even if bad case was saved, guard prompt won't include it if you:

- Started a new chat session (new UUID)
- Changed browser/window
- Lost session context

**The learning only works within SAME session.**

### Solution 2A: Verify session ID is persistent

In chat_ui.html, check that:

```javascript
// Session should be stored and reused
let sessionId = localStorage.getItem("sessionId");
if (!sessionId) {
  sessionId = uuid4();
  localStorage.setItem("sessionId", sessionId);
}
// Use sessionId for all chat requests
```

### Solution 2B: Check what session_id has the bad case

```bash
# In Supabase SQL Editor:
SELECT DISTINCT session_id FROM bad_cases
  WHERE reason LIKE '%Enoch%' OR expected_output LIKE '%Enoch%';
```

Then use that exact session_id for your next question.

---

### 3. ⚠️ **Guard prompt IS being built but LLM isn't following it**

If bad_case was saved and session_id matches, the guard SHOULD be injected.
But LLM might still not follow it if:

- **Temperature too high** → LLM is creative, ignores guidance
  - Solution: Lower temperature in API call or chat settings

- **Guard prompt text is too generic** → No specific enough
  - Solution: Make `expected_output` in bad_case very specific
  - Instead of: "Correct information about Enoch CHIU"
  - Use: "Enoch CHIU is a researcher specializing in X, published Y, affiliated with Z"

- **Expected output not in guard** → Injection didn't work
  - Solution: Run diagnostic script (see below)

---

### 4. ⚠️ **Sentiment analyzer not detecting feedback** (Low confidence)

The first filter is sentiment analysis. If it doesn't detect dissatisfaction:

```python
# User message must contain dissatisfaction signals:
is_dissatisfied = sentiment_analyzer.is_dissatisfied(user_feedback)
```

**If `is_dissatisfied = False`**: orchestrator stops immediately, no bad case created.

### Solution 4A: Use explicit dissatisfaction language

❌ Might be missed:

- "I disagree"
- "That's weird"
- "Hmm"

✅ Always detected:

- "Wrong!"
- "That's not right!"
- "Incorrect:"
- "No, that's false"
- "Hallucination"
- "Wrong answer"

---

## Step-by-Step Diagnostic

### Step 1: Run the diagnostic script

```bash
# Replace with your actual session ID
python scripts/diagnose_guard_injection.py "your-session-id-here"
```

This will show:

- ✓ All bad_cases in the session
- ✓ The exact guard prompt that would be injected
- ✓ All messages in the session
- ✓ Audit status for each message

### Step 2: Check Supabase directly (if script doesn't help)

```sql
-- Check if bad case was saved
SELECT id, reason, category, expected_output, session_id
FROM bad_cases
WHERE reason LIKE '%Enoch%' OR expected_output LIKE '%Enoch%'
ORDER BY created_at DESC;

-- Check if AI audit was triaged as bad_case
SELECT id, status, verdict, analysis_label, session_id
FROM ai_audits
ORDER BY created_at DESC LIMIT 20;

-- Check session messages
SELECT id, role, content, created_at
FROM chat_messages
WHERE session_id = 'YOUR-SESSION-ID'
ORDER BY created_at;
```

### Step 3: Verify guard building logic

The guard should include entries like:

```
[LEARNED CORRECTION PATTERNS]
- Avoid pattern: 'Wrong info about Enoch' -> Prefer: 'Enoch CHIU is...'

[R/C - HIGH PRIORITY CONSTRAINTS]
- Enoch CHIU (priority=HIGH, seen=1)
```

If these are missing, the bad case isn't being fetched or formatted correctly.

---

## Testing End-to-End

### Test A: Simple Factual Correction

**Turn 1 (User):**

```
Who is Enoch CHIU? Tell me about him.
```

**Turn 1 (LLM):**

```
I don't have specific information about Enoch CHIU in my training data...
```

**Turn 2 (User):**

```
Wrong! Enoch CHIU is a machine learning researcher who specializes in NLP and has published papers on transformers.
```

✓ System should detect bad_case and save to database

**Turn 3 (User):**

```
Can you tell me more about Enoch CHIU's research?
```

⚠️ **Expected**: LLM remembers and provides ML/NLP context
❌ **Actual**: LLM still gives generic answer
→ Run diagnostic to see why

---

## Common Issues & Fixes

| Issue                       | Cause                             | Fix                                                 |
| --------------------------- | --------------------------------- | --------------------------------------------------- |
| Bad case not saved          | Triage classified as "preference" | Use keywords: "wrong", "incorrect", "hallucination" |
| Guard not injected          | Session ID changed                | Store session ID in localStorage, reuse it          |
| LLM ignores guard           | Temperature too high              | Lower temperature to 0.3-0.5 during learning        |
| Expected answer too generic | Guard text not specific           | Provide concrete, detailed expected answer          |
| Nothing in bad_cases table  | Bad case row insertion failed     | Check error logs, verify `session_id` is UUID       |
| Guard built but empty       | Fetching failed                   | Run diagnostic script to see actual guard prompt    |

---

## Debug Logging

To see detailed logs of the learning loop:

### In API logs:

```bash
# Watch for these log lines:
ERROR: "Feedback learning skipped: sentiment not dissatisfied"
  → Feedback wasn't detected as complaint

ERROR: "Feedback learning skipped: unable to resolve corrected assistant message"
  → Couldn't find which assistant message to correct

INFO: "Captured feedback learning case: [ID]"
  → Bad case was successfully saved! ✓

WARNING: "Failed saving correction to bad_cases"
  → Server error while saving bad case
```

### In Python (if running locally):

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Then run your chat request to see detailed logs
```

---

## Next Steps

1. **Run diagnostic**: `python scripts/diagnose_guard_injection.py <session_id>`
2. **Review guard prompt** output to see what's being injected
3. **Check bad_cases table** in Supabase to confirm save
4. **Adjust expected_output** to be more specific if needed
5. **Test again** in same session with same session_id
6. **If still not working**: Check server logs and run diagnostic again

---

## Files Reference

- **Feedback learning**: `learn_from_chat/orchestrator.py`
- **Bad case saving**: `learn_from_chat/db_handler.py`
- **Guard building**: `process_framework/api/feedback.py` (functions: `build_session_guard`, `build_guard_prompt`)
- **Guard injection**: `process_framework/api/routes/chat.py` (lines ~278-280)
- **Diagnostic tool**: `scripts/diagnose_guard_injection.py`
