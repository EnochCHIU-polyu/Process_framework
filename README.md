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

## Project layout

```text
Project_framework/
├── README.md                    # main start guide
├── chat_ui.html
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

## Troubleshooting (short)

- API cannot start:
  - Check `.env` variables and installed dependencies
- Supabase errors:
  - Re-check `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and migration applied
- Learning loop not obvious:
  - Keep same session and ensure bad cases are actually flagged/inserted

Useful scripts/tools:

- `scripts/diagnose_learning_loop.py`
- `tests/verify_clustering.py`

---

## Suggested reading order

1. `README.md` (this file)
2. `chat_ui.html` + API docs (`/docs`)
3. `examples/demo_full_process.py`
4. `examples/example_bad_case_learning.py`
5. Specific file in `docs/` only if needed
