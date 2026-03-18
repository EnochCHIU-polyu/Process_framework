"""
Configuration for the PROCESS Chat Auditing API.

All settings are loaded from environment variables (or a .env file).
Required vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
Optional vars: OLLAMA_BASE_URL, OLLAMA_MODEL
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Server
    cors_origins: list[str] = ["*"]


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
