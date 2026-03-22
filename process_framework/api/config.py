"""
Configuration for the PROCESS Chat Auditing API.

All settings are loaded from environment variables (or a .env file).
Required vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
Optional vars: OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_BACKEND,
               OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    # LLM backend selector: "ollama" (default) | "openai"
    # Set to "openai" to use any OpenAI-compatible API (Poe, OpenAI, Azure, etc.)
    llm_backend: str = "ollama"

    # Ollama backend (used when llm_backend="ollama")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # OpenAI-compatible backend (used when llm_backend="openai")
    # Works with Poe (base_url="https://api.poe.com/v1"),
    # OpenAI (base_url="https://api.openai.com/v1"), or any compatible endpoint.
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.poe.com/v1"
    openai_model: str = "deepseek-v3.2"  # Default logic model
    
    # Chat-specific model (can be different for testing/hallucinations)
    # If not set, falls back to openai_model
    chat_openai_model: Optional[str] = None
    chat_ollama_model: Optional[str] = None

    # Server
    cors_origins: list[str] = ["*"]


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
