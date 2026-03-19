# Automatic Learning Loop - Setup & Activation

## The Question: Does It Auto-Work?

**Answer: YES, but with one prerequisite.** You need to flag bad cases **once**, then everything else runs automatically.

---

## 🎯 What's Automatic vs Manual

### AUTOMATIC (No Action Needed)

- ✅ Auto audit detects issues
- ✅ Session guard built from findings
- ✅ Guard injected into next response
- ✅ Model learns from previous mistakes

### MANUAL (One-Time Per Issue)

- ⚙️ Flag bad cases: `framework.record_bad_case(...)`

---

## 🔄 Complete Automatic Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    CHAT SESSION STARTS                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │  User sends chat message         │
        └────────────┬─────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────────┐
        │  [AUTOMATIC] Auto Audit runs     │
        │  - Analyzes assistant response   │
        │  - Uses LLM Judge to detect      │
        │    hallucinations, quality issues│
        └────────────┬─────────────────────┘
                     │
                     ▼
        ┌──────────────────────────────────┐
        │  Issues detected?                │
        └────────────┬─────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
  ┌──────────────┐         ┌─────────────┐
  │     YES      │         │      NO     │
  └────────┬─────┘         └──────┬──────┘
           │                      │
           ▼                      ▼
  ┌──────────────────────┐  ┌────────────┐
  │ [MANUAL - Do This]   │  │ Continue   │
  │ Flag bad case:       │  │ chatting   │
  │ framework.           │  │ (next turn)│
  │   record_bad_case()  │  └────────────┘
  └────────────┬─────────┘
               │
               ▼
  ┌──────────────────────────────────┐
  │ [AUTOMATIC] Bad case stored      │
  │ in Supabase with:                │
  │ - Root cause category            │
  │ - Ignored keywords               │
  │ - Improvement suggestions        │
  └────────────┬─────────────────────┘
               │
               ▼ (Next chat turn in same session)
  ┌──────────────────────────────────┐
  │ [AUTOMATIC] Session Guard built  │
  │ from previous bad cases:         │
  │ "Remember: France = Paris,       │
  │  not London"                     │
  └────────────┬─────────────────────┘
               │
               ▼
  ┌──────────────────────────────────┐
  │ [AUTOMATIC] Guard INJECTED       │
  │ into system prompt before        │
  │ model generates response         │
  └────────────┬─────────────────────┘
               │
               ▼
  ┌──────────────────────────────────┐
  │ [AUTOMATIC] LLM sees guard       │
  │ and avoids previous mistakes     │
  └────────────┬─────────────────────┘
               │
               ▼
  ┌──────────────────────────────────┐
  │ Quality IMPROVED:                │
  │ - Correct response generated     │
  │ - Model learned from feedback    │
  └──────────────────────────────────┘
```

---

## ⚡ Minimal Setup (3 Steps)

### Step 1: Start the API Server

```bash
cd /Users/yeechiu/Documents/GitHub/mobile-app-assignment-1/AI-Assignment-1/AI-assignment-2/Process_framework

source .venv/bin/activate

uvicorn process_framework.api.main:app --reload
# Server running at http://localhost:8000
```

### Step 2: Send Chat Messages

```bash
# Use the chat UI or API to add messages
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "user_123",
    "message": "What is the capital of France?"
  }'
```

### Step 3: Flag Bad Cases (When Detected)

```python
from process_framework import ProcessFramework, BadCaseCategory, EvaluationCase, ScenarioType

framework = ProcessFramework()
framework.setup_purpose("Chat auditing")

case = EvaluationCase(
    scenario_type=ScenarioType.QA,
    user_input="What is the capital of France?",
    actual_output="London",  # Wrong!
)

# THIS IS THE ONLY MANUAL STEP
framework.record_bad_case(
    evaluation_case=case,
    category=BadCaseCategory.HALLUCINATION,
    description="Model hallucinated wrong capital",
    ignored_keywords=["France", "capital"],
)

print("✓ Bad case recorded. Everything else is automatic!")
```

**After this:** All subsequent responses in the same session automatically get the guard injection.

---

## 🤖 What Happens Automatically After You Record

```python
# AUTOMATIC: Session guard built
guard = """
⚠️ AUDIT FINDINGS FROM THIS SESSION:
[HALLUCINATION] Model confused cities
  → Add geographic verification (RAG layer)

[CONSTRAINT KEYWORDS TO REMEMBER]
⚫ 'France' (missed 1 time)
⚫ 'capital' (missed 1 time)

INSTRUCTION: Verify facts before responding!
"""

# AUTOMATIC: Guard injected into next response
system_prompt = default_system_prompt + guard

# AUTOMATIC: Model sees the guard
response = llm.generate(
    system_message=system_prompt,  # ← Guard included!
    messages=conversation_history
)

# RESULT: Model avoids repeating mistakes
# Expected: "The capital of France is Paris." ✓
```

---

## 📊 Real-World Example: Full Cycle

### Turn 1: (Automatic Auto Audit)

```
User: "What is the capital of France?"
Model: "The capital of France is London."
[Auto Audit] ⚠️ DETECTED: Hallucination (risk score: 0.85)
```

### Action Required (You): Record the bad case

```python
framework.record_bad_case(...)  # ← Only this is manual
```

### Turn 2+: (Everything Automatic)

```
User: "Can you repeat that?"
[Auto Audit] ✓ Session has 1 prior bad case
[Session Guard] ✓ Building from hallucination findings
[Guard Injected] ✓ Model sees: "Paris, not London"
Model: "The capital of France is Paris." ✓ CORRECT
[Auto Audit] ✓ No hallucination detected this time
```

---

## 🎛️ Control Levels

### Full Automatic (Recommended)

```python
# Set up once, forget about it
framework = ProcessFramework()
framework.setup_purpose("...")

# Bad cases recorded manually when needed
# Session guards injected automatically on every turn
# No further action needed
```

### Fine-Grained Control

```python
# Access individual components if needed
audit_results = await run_auto_audit(settings, session_id)
framework.record_bad_case(...)
report = framework.build_bad_case_report(...)
guard = await build_session_guard(session_id, settings)
messages = inject_guard_prompt(messages, guard)
```

---

## ✅ Checklist: Is It Working?

- [ ] FastAPI server running (`uvicorn ... --reload`)
- [ ] Chat turns being added to Supabase
- [ ] Auto audit detects some issues
- [ ] You record bad cases when found
- [ ] Next turn in same session shows improvement
- [ ] Check Supabase `bad_cases` table has records

---

## 🔍 How to Verify It's Working

### Check 1: Supabase has bad cases

```sql
SELECT * FROM bad_cases ORDER BY created_at DESC LIMIT 5;
```

### Check 2: Session guard being built

```python
from process_framework.api.feedback import build_session_guard
guard = await build_session_guard(session_id, settings)
print(guard)  # Should show issues + improvement tips
```

### Check 3: Messages have guard injected

```python
# In the chat API, before generating response:
messages_with_guard = inject_guard_prompt(messages, guard)
# These messages should include the guard in system prompt
```

---

## 💡 TL;DR

| What                       | Automatic? | How Often                 |
| -------------------------- | ---------- | ------------------------- |
| Auto audit detects issues  | ✅ YES     | Every chat turn           |
| Record bad case            | ⚙️ MANUAL  | Once per issue            |
| Build session guard        | ✅ YES     | Once per session          |
| Inject guard into response | ✅ YES     | Every turn with bad cases |
| Model learns from guard    | ✅ YES     | Every turn                |
| Quality improves           | ✅ YES     | Each iteration            |

**Bottom Line:** Record bad cases once, everything else runs automatically on every chat turn.

---

## 🚀 Next Steps

1. Run the example: `python example_bad_case_learning.py`
2. Start the API server: `uvicorn process_framework.api.main:app --reload`
3. Send chat messages and see auto audit in action
4. Flag a bad case: `framework.record_bad_case(...)`
5. Send another message in same session
6. Watch the guard kick in automatically! 🎉

---

## 📞 Questions?

- **"How do I know if guard is being used?"** → Check Supabase logs and monitor LLM responses for improvements
- **"Can I test without Supabase?"** → Run `example_bad_case_learning.py` (no DB needed)
- **"How long does improvement take?"** → Usually 1-2 iteration cycles
- **"What if I don't flag bad cases?"** → Auto audit still runs, but guard won't be built (no learning loop)
