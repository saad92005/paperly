"""Settings loaded from env / .env. Every limit and model name lives here, never in code."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env sits at the repo root (two levels above apps/api).
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, extra="ignore")

    app_name: str = "Paperly"
    app_env: Literal["dev", "test", "prod"] = "dev"
    version: str = "0.1.0"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Database / auth
    database_url: str = ""
    # Better Auth (runs in the web app) signs short-lived JWTs; we verify them via its JWKS.
    auth_jwks_url: str = ""
    auth_jwt_issuer: str = ""
    auth_jwt_audience: str = "paperly-api"

    # Providers (order = fallback order)
    route_chat: str = "groq,gemini,openrouter"
    route_summary: str = "gemini,groq"
    route_vision: str = "gemini"
    groq_api_key: str = ""
    groq_chat_model: str = ""
    gemini_api_key: str = ""
    gemini_chat_model: str = ""
    openrouter_api_key: str = ""
    openrouter_chat_model: str = ""
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_enabled: bool = False
    ollama_model: str = ""
    # openai_compat uses every provider that has a key; with no key, chat falls back to
    # extractive answers (quoted sentences, no generation) so the app still works at $0.
    llm_provider_impl: Literal["stub", "openai_compat"] = "openai_compat"
    embeddings_provider: Literal["stub", "fastembed"] = "fastembed"
    embeddings_model: str = "BAAI/bge-small-en-v1.5"
    embeddings_dim: int = 384
    reranker: Literal["stub", "flashrank"] = "flashrank"
    model_cache_dir: str = str(Path(__file__).resolve().parents[1] / ".models")
    abstain_threshold: float = 0.15  # FlashRank score
    abstain_vsim: float = 0.62  # bge-small cosine; calibrated in docs/07
    pdf_parser_chain: str = "arxiv_html,grobid,pdfplumber"
    grobid_url: str = ""

    # Limits
    max_upload_mb: int = 25
    max_pages_free: int = 100
    quota_questions_per_day: int = 50
    quota_imports_per_day: int = 10
    quota_compares_per_day: int = 5
    worker_mode: Literal["inprocess", "off"] = "inprocess"
    worker_concurrency: int = 2
    rate_limit_per_minute: int = 120

    # Observability
    log_level: str = "INFO"
    sentry_dsn: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    contact_email: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str:
        return self.auth_jwks_url or f"{self.web_base_url.rstrip('/')}/api/auth/jwks"

    @property
    def jwt_issuer(self) -> str:
        return self.auth_jwt_issuer or self.web_base_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
