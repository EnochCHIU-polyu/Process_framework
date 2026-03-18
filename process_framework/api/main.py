"""
FastAPI application for the PROCESS Chat Auditing API.

Run with:
    uvicorn process_framework.api.main:app --reload
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from process_framework.api.config import Settings, get_settings
from process_framework.api.routes.audit import router as audit_router
from process_framework.api.routes.chat import router as chat_router
from process_framework.api.routes.process import router as process_router

_startup_settings = get_settings()

app = FastAPI(
    title="PROCESS Chat Auditing API",
    description=(
        "LLM chat service with Ollama/OpenAI backend, Supabase persistence, "
        "hallucination marking, and PROCESS-framework pipeline integration."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_startup_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(audit_router)
app.include_router(process_router)


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    """Simple liveness check; also reports the active LLM backend."""
    return {"status": "ok", "llm_backend": settings.llm_backend}
