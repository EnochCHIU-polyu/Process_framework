# learn_from_chat

Feedback-driven learning module for PROCESS chat.

This module captures high-value user corrections (for example: "This is wrong, the correct answer is ...") and stores them in Supabase so future responses can improve.

---

## Goal

Process the latest user message and decide whether the user is dissatisfied with an LLM answer. If yes, extract correction information and persist it as a learnable bad case.

---

## Architecture

Hybrid pipeline:

1. **Sentiment screening (BERT/local-first)**
   - File: `sentiment.py`
   - Uses HuggingFace sentiment pipeline when available
   - Falls back to keyword rules if `transformers` is unavailable

2. **Correction extraction (LLM/GPT)**
   - File: `correction_extractor.py`
   - Calls existing project LLM abstraction (`process_framework.api.llm.call_llm`)
   - Extracts structured JSON:
     - `is_correction`
     - `error_type`
     - `correct_answer`
     - `reason`
     - `ignored_keywords`

3. **Persistence to Supabase**
   - File: `db_handler.py`
   - Maps extracted `error_type` to valid `bad_cases.category`
   - Inserts into `bad_cases` with context fields

4. **End-to-end orchestration**
   - File: `orchestrator.py`
   - Resolves context from chat messages
   - Runs sentiment -> extraction -> save

---

## Runtime integration

Integrated from:

- `process_framework/api/routes/chat.py`

After `/chat` persistence, the system starts a non-blocking background task:

- `process_feedback_and_learn(session_id, messages, settings)`

This keeps user-facing latency low while still capturing learning signals.

---

## Data written to Supabase

Target table:

- `bad_cases`

Main fields written:

- `message_id` (assistant message being corrected)
- `session_id`
- `reason`
- `category` (mapped to allowed enum)
- `expected_output` (user-corrected answer)
- `actual_output` (assistant answer)
- `notes` (question + user feedback)
- `ignored_keywords`

---

## Classification Standards

### Three main classifications

The LLM triage function (`triage_feedback()` in `correction_extractor.py`) classifies user feedback into:

#### 1. `bad_case` — Factual/Model Error

User points out factual wrongness, contradiction, or hallucination.

**When to use:**

- Model generated incorrect information
- Answer contains factual contradictions
- Model ignored constraints or requirements
- Wrong entity or logic in response

**Error types:**

- `hallucination` — Fabricated or incorrect information
- `factual_error` — Entity/factual inconsistency
- `intent_misunderstanding` — Missed keywords or constraints
- `constraint_ignored` — Ignored requirements
- `logical` — Reasoning/coherence error
- `referential` — Citation/attribution error

**Example:**

```
User Q: "What is the capital of France?"
Model A: "London"  [WRONG]
User Feedback: "That's wrong, it's Paris."
→ Classification: bad_case
→ Error type: hallucination
→ Correct answer: Paris
```

**Storage:** Persisted in `bad_cases` table with category mapped from error_type.

#### 2. `preference` — User Style/Format Request

User requests different style, tone, detail level, or formatting (NOT a factual error).

**When to use:**

- User wants different tone (more/less casual, formal, etc.)
- User requests different length (shorter/longer, more/less detail)
- User wants different format (bullet points, table, numbered list, etc.)
- User wants different style or presentation
- User asks for reformatting of correct information

**Error type:** `tone_issue`

**Example:**

```
User Q: "Explain quantum computing"
Model A: "Quantum computing uses qubits..." [CORRECT but verbose]
User Feedback: "Can you make it shorter?"
→ Classification: preference
→ Error type: tone_issue
```

**Storage:** Marked as reviewed (`verdict=ok`) in `ai_audits` but NOT stored as bad_case. Metadata only.

#### 3. `unclear` — Insufficient Evidence

Feedback doesn't clearly indicate bad_case or preference.

**When to use:**

- Ambiguous feedback without clear direction
- Partial or incomplete corrections
- Mixed signals (some factual + some preference)
- Insufficient information to classify

**Confidence:** Typically 0.3-0.5 (low confidence)

**Example:**

```
User Feedback: "I'm not sure about that..."
→ Classification: unclear
→ Confidence: 0.3
```

**Storage:** Marked as reviewed for manual inspection. Does not trigger learning loop.

### Triage prompt (LLM)

The LLM uses this prompt to classify:

```
You are an audit triage assistant.

Determine whether the user's feedback indicates:
1) factual/model-error (should become bad_case), OR
2) user preference/style request (should be reviewed but not bad_case), OR
3) unclear.

Return JSON only with keys:
{
    "classification": "bad_case" | "preference" | "unclear",
    "error_type": "hallucination" | "factual_error" | "intent_misunderstanding"
                  | "constraint_ignored" | "tone_issue" | "other",
    "summary": string,
    "confidence": number,
    "correct_answer": string | null,
    "ignored_keywords": string[]
}

Guidelines:
- Use bad_case when user points out factual wrongness, contradiction, or hallucination.
- Use preference when user mainly requests style, tone, detail level, or formatting.
- Use unclear when evidence is insufficient.
- confidence must be between 0 and 1.
```

### Error type mapping

`error_type` from extractor is mapped to `bad_cases.category` (only for bad_case classification):

| error_type                | category               | note                           |
| ------------------------- | ---------------------- | ------------------------------ |
| `hallucination`           | `hallucination`        | Fabricated/incorrect info      |
| `factual_error`           | `factual`              | Entity/factual inconsistency   |
| `intent_misunderstanding` | `intent_understanding` | Missed keywords/constraints    |
| `constraint_ignored`      | `user_experience`      | Ignored requirements           |
| `logical`                 | `logical`              | Reasoning/coherence error      |
| `referential`             | `referential`          | Citation/attribution error     |
| `tone_issue` / `other`    | `user_experience`      | Style/format (preference only) |

### Triage output format

Each classification includes:

```json
{
  "classification": "bad_case" | "preference" | "unclear",
  "error_type": "string",
  "summary": "Human-readable explanation",
  "confidence": 0.0-1.0,
  "correct_answer": "string or null",
  "ignored_keywords": ["keyword1", "keyword2"]
}
```

### Downstream flow

After classification:

1. **bad_case (confidence ≥ 0.5)**
   - Stored in `bad_cases` table
   - AI audit marked `status=suspected_hallucination`, `verdict=bad_case`
   - Bad case clustered into learned patterns
   - Guard prompt injected into next response to prevent repeat

2. **preference or bad_case with low confidence**
   - AI audit marked `status=reviewed`, `verdict=ok`
   - Stored as metadata in `ai_audits.analysis_label` = "preference" or "unclear"
   - Does NOT become bad_case
   - Does NOT trigger learning loop

3. **unclear**
   - AI audit marked for manual inspection
   - Confidence signal low (0.3-0.5)
   - No automatic action taken

---

## Dependencies

Declared in project optional API dependencies (`pyproject.toml`):

- `transformers>=4.36`
- `torch>=2.0`

Install with:

```bash
pip install -e ".[api,dev]"
```

---

## Notes

- If sentiment model cannot load, module continues in keyword-fallback mode.
- Failures in extraction or DB insert are non-fatal and do not break `/chat` responses.
- This module is designed to be extensible for richer classifier models later.
