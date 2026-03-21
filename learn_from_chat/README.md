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

## Error type mapping

`error_type` from extractor is mapped to `bad_cases.category`:

- `hallucination` -> `hallucination`
- `factual_error` -> `factual`
- `intent_misunderstanding` -> `intent_understanding`
- `constraint_ignored` -> `user_experience`
- `tone_issue` / `other` -> `user_experience`

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
