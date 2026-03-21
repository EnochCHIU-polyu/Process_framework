# PROCESS Framework (Start Here)

This is the single main guide for starting and running the project.

If you read only one file, read this README.

---

## What this project is

The project provides:

- A 7-stage `PROCESS` AI review framework (`Purpose`, `Resources`, `Optimization`, `Count`, `Effectiveness`, `Standards`, `Scrutiny`)
- A FastAPI backend for chat + auditing
- Supabase persistence for chat history, audits, bad cases, and learned patterns
- A simple browser chat UI (`chat_ui.html`)
- Automated bad-case learning with clustering/pattern reuse
- A hybrid feedback-learning module in `learn_from_chat/` (BERT detection + LLM extraction)

Core package: `process_framework/`

---

## Quick start (recommended)

## 1) Prerequisites

- Python `3.9+`
- A Supabase project
- One LLM backend:
  - Ollama (local), or
  - OpenAI-compatible endpoint

## 2) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[api,dev]"
```

## 3) Configure environment

```bash
cp .env.example .env
```

Set at minimum in `.env`:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `LLM_BACKEND`

For Ollama:

- `LLM_BACKEND=ollama`
- `OLLAMA_BASE_URL=http://localhost:11434`
- `OLLAMA_MODEL=llama3.1:8b` (or any installed model)

For OpenAI-compatible:

- `LLM_BACKEND=openai`
- `OPENAI_API_KEY=...`
- `OPENAI_BASE_URL=...` (optional)
- `OPENAI_MODEL=...`

## 4) Apply database migration

Fastest path:

```bash
bash supabase/setup_and_migrate.sh
```

Alternative: run SQL manually from:

- `supabase/migrations/001_chat_auditing.sql`

## 5) Start API server

```bash
uvicorn process_framework.api.main:app --reload
```

Then open:

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## 6) Open chat UI

```bash
open chat_ui.html
```

---

## Typical first run flow

1. Start API server
2. Send a message from UI or `/chat`
3. Flag a poor response as a bad case
4. Continue chat in same session
5. Confirm improved guidance from previous bad-case patterns

---

## Feedback-learning module

This project includes a dedicated sub-module for learning from user corrections:

- Path: `learn_from_chat/`
- Purpose: detect dissatisfaction in latest user messages and capture correction data
- Output target: `bad_cases` table in Supabase for future learning loops

For setup, internals, and extension notes, read:

- `learn_from_chat/README.md`

---

## Audit classification standards

User feedback is classified into three categories:

### 1. `bad_case` — Factual/Model Error

Used when user feedback indicates **factual wrongness, contradiction, or hallucination**.

**Criteria:**

- Model generated incorrect information (hallucination)
- Answer contains factual contradictions
- Model ignored constraints or requirements
- Wrong entity/logic in response

**Error types:**

- `hallucination` — Fabricated or incorrect information
- `factual` — Entity/factual inconsistency
- `logical` — Reasoning/coherence error
- `referential` — Citation/attribution error
- `intent_misunderstanding` — Ignored keywords/constraints

**Outcome:** Stored in `bad_cases` table → clustered into learned patterns → injected into guard prompts to prevent repeats.

### 2. `preference` — User Style/Format Request

Used when user feedback is mainly about **style, tone, detail level, or formatting** (NOT factual error).

**Criteria:**

- User wants different tone (casual, formal, etc.)
- User requests different length (shorter, more detailed)
- User wants different format (bullet points, table, etc.)
- User wants different presentation style

**Error type:** `tone_issue`

**Outcome:** Marked as reviewed (`verdict=ok`) but NOT stored as bad_case. Treated as feedback signal only.

### 3. `unclear` — Insufficient Evidence

Used when feedback **doesn't clearly fall** into bad_case or preference.

**Criteria:**

- Ambiguous feedback without clear direction
- Partial or incomplete corrections
- Mixed signals (partial factual + partial preference)

**Outcome:** Marked as reviewed for manual inspection. Low confidence signal.

### Classification flow

1. User provides feedback on assistant response
2. LLM Triage classifies via `triage_feedback()` (in `learn_from_chat/correction_extractor.py`)
3. Each classification includes:
   - `classification`: bad_case | preference | unclear
   - `error_type`: specific root cause
   - `summary`: human-readable explanation
   - `confidence`: 0.0-1.0 LLM confidence score
   - `correct_answer`: (if bad_case) the right answer
   - `ignored_keywords`: keywords model missed (for intent types)

4. Status assignment based on classification:
   - `bad_case` → `status=suspected_hallucination`, stored in `bad_cases` table
   - `preference` → `status=reviewed`, `verdict=ok`, metadata only
   - `unclear` → `status=reviewed`, `verdict=ok`, marked for manual review

### Full details

See `learn_from_chat/README.md` → **Classification Standards** for implementation details and triage prompt.

---

## Project layout

```text
Project_framework/
├── README.md                    # main start guide
├── chat_ui.html
├── learn_from_chat/            # Feedback-learning sub-module
│   ├── sentiment.py
│   ├── correction_extractor.py
│   ├── db_handler.py
│   ├── orchestrator.py
│   └── README.md
├── examples/                    # Demos and framework examples
│   ├── demo_full_process.py
│   └── example_bad_case_learning.py
├── scripts/                     # Deployment and diagnostic utilities
│   ├── rest_api_deploy.py
│   └── diagnose_learning_loop.py
├── process_framework/           # Core library
│   ├── framework.py
│   ├── core/
│   ├── stages/
│   └── api/
├── supabase/                    # Database migrations
│   ├── migrations/
│   └── setup_and_migrate.sh
├── tests/                       # Unit and integration tests
└── docs/                        # Secondary documentation
```

---

## Main commands

Install + setup:

```bash
pip install -e ".[api,dev]"
```

Run API:

```bash
uvicorn process_framework.api.main:app --reload
```

Run tests:

```bash
pytest -v
```

Run one test file:

```bash
pytest tests/test_framework.py -v
```

---

## Where to find extra docs

All less-important/supporting markdown files are now in:

- `md/`

Use these only when needed (deployment details, troubleshooting notes, status summaries, architecture notes).

---

## How the learning loop works (global learning across all chats)

### ⚡ What's Automatic

Every chat request:

1. ✅ Guard is built AUTOMATICALLY before LLM call
2. ✅ Guard includes bad cases from THIS session + ALL other sessions (global)
3. ✅ Guard is INJECTED into system message automatically
4. ✅ When user flags correction, bad_case is saved AUTOMATICALLY
5. ✅ Auto-audit runs in BACKGROUND to detect hallucinations

### 🔄 The Flow

**Scenario: User flags "Enoch CHIU" correction in Chat A → Should apply to Chat B and beyond**

1. **Chat A - User flags a correction** (e.g., "Wrong! Enoch CHIU is..."):
   - System detects dissatisfaction in user message
   - LLM triage classifies as `bad_case` or `preference`
   - If `bad_case`: **saved to database with session_id**

2. **Chat A - SAME session, next turn** OR **Chat B - ANY new session**:
   - `build_session_guard()` fetches:
     - ✓ Session-specific bad cases (this chat)
     - ✓ **Recent GLOBAL bad cases** (from all other chats/sessions)
   - Combines all bad cases into guard prompt
   - Clusters patterns to deduplicate
   - Injects guard as system message BEFORE calling LLM
   - LLM receives: `[system: GUARD_PROMPT] + [user messages]`

3. **LLM responds** with combined knowledge:
   - Knows about "Enoch CHIU" from any previous chat
   - Avoids repeating corrections from other sessions
   - Applies learned constraints globally

### ✨ Key Difference: GLOBAL Learning

Before: Bad cases only worked in SAME session  
**Now: Bad cases apply to ALL chats** ✓

- Flag "Enoch CHIU" in Chat A → LLM knows it in Chat B, Chat C, etc.
- Each chat learns from corrections in ALL OTHER chats
- No need to keep same session ID anymore
- Knowledge accumulates continuously

### Guard Prompt Example

What gets injected for EVERY LLM call:

```
[GLOBAL AUDIT KNOWLEDGE & FEEDBACK]
The following issues have been identified across current and previous chat
sessions. You MUST apply these lessons across ALL chat topics to ensure quality
and avoid repeating known failure patterns (these are learned from corrections
by users):

[PROCESS-LOOP POLICY SNAPSHOT]
- Fresh issues (this session): 1
- Learned patterns (accumulated): 3 clusters (μ 5 occurrences)

[P/O - PURPOSE & OPTIMIZATION RULES]
- [HALLUCINATION] x1: Use only verifiable facts; explicitly say uncertain...

[R/C - HIGH PRIORITY CONSTRAINTS]
- Enoch CHIU (priority=HIGH, seen=3)   ← Known from OTHER sessions too!
- AI researcher (priority=NORMAL, seen=2)

[LEARNED CORRECTION PATTERNS]
- Avoid: 'Generic bio' → Prefer: 'Enoch CHIU is [specific resume]'
- Avoid: '[Person] is unknown' → Provide concrete details if exists

[S/S - SELF SCRUTINY CHECKLIST BEFORE RESPONDING]
- Did I satisfy all user constraints and keywords?
- Did I remove any unsupported / speculative claims?
- Is the answer concise and directly actionable?
- Did I avoid repeating previously flagged failure patterns?
```

### Diagnosing the Learning Loop

```bash
# Anytime, run this to inspect what guard prompt would be built:
python scripts/diagnose_guard_injection.py <session_id>
```

Output shows:

- ✓ Session-specific bad cases
- ✓ **Global bad cases** (from other chats)
- ✓ Combined guard prompt LLM will receive
- ✓ Diagnostics & recommendations

### Troubleshooting: Why isn't LLM learning globally?

| Issue                     | Cause                                    | Fix                                                       |
| ------------------------- | ---------------------------------------- | --------------------------------------------------------- |
| No bad cases in DB        | Feedback wasn't triaged as bad_case      | Use explicit language: "Wrong!", "Hallucination", "False" |
| Guard is empty            | No bad cases but also no global patterns | Need to flag at least one correction first                |
| LLM ignores guide         | Temperature too high                     | Lower to 0.3-0.5, or guard auto-reduces it                |
| Expected answer vague     | "Correct info" not specific              | Use: "Enoch CHIU specializes in NLP and transformers"     |
| Still only session-scoped | Old code still running                   | Restart API server to load new code                       |

---

## Troubleshooting (short)

- API cannot start:
  - Check `.env` variables and installed dependencies
- Supabase errors:
  - Re-check `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and migration applied
- **LLM not learning from bad_cases (GLOBAL, across all chats)**:
  - Bad cases NOW apply to all chats/sessions (not just same session)
  - Run diagnostic: `python scripts/diagnose_guard_injection.py <session_id>`
    - Shows session-specific + global bad cases combined
    - Displays exact guard prompt that would be injected
    - Indicates which bad cases come from other sessions
  - Verify `expected_output` is specific and concrete
  - Check server logs for `save_user_correction` errors
  - See troubleshooting table in "How the learning loop works" section
- Learning takes time:
  - Wait 1-2 seconds after submitting feedback for DB save
  - Then send NEXT message to see guard in effect
  - Guard applies to EVERY subsequent message
  - Multiple corrections compound the effect

Useful scripts/tools:

- `scripts/diagnose_guard_injection.py <session_id>` — Shows session + GLOBAL bad cases and combined guard prompt
- `scripts/diagnose_learning_loop.py` — Check bad case clustering
- `tests/verify_clustering.py` — Verify pattern clustering logic

---

## Suggested reading order

1. `README.md` (this file)
2. `chat_ui.html` + API docs (`/docs`)
3. `examples/demo_full_process.py`
4. `examples/example_bad_case_learning.py`
5. Specific file in `docs/` only if needed
