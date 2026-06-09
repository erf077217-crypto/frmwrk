from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralized configuration driven by environment variables.

    All secrets are read from the environment or a .env file.
    No hardcoded credentials anywhere.
    """

    # ── General ──────────────────────────────────────────────
    app_name: str = "AI Platform"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False

    # ── Provider API Keys & Endpoints ───────────────────────
    openai_api_key: Optional[str] = None
    openai_org_id: Optional[str] = None

    anthropic_api_key: Optional[str] = None

    gemini_api_key: Optional[str] = None

    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_default_model: str = "llama3"

    # ── Provider Flags ──────────────────────────────────────
    enable_openai: bool = True
    enable_anthropic: bool = True
    enable_gemini: bool = True
    enable_ollama: bool = True

    # ── Workspace ───────────────────────────────────────────
    workspace_dir: str = "/tmp/workspace"
    db_path: str = "/tmp/workspace/data.db"

    # ── Server ──────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:80",
    ]

    # ── Environment validation ──────────────────────────────
    validate_env: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def providers_enabled(self) -> dict[str, bool]:
        return {
            "openai": self.enable_openai,
            "anthropic": self.enable_anthropic,
            "gemini": self.enable_gemini,
            "ollama": self.enable_ollama,
        }

    @property
    def provider_keys_present(self) -> dict[str, bool]:
        return {
            "openai": self.openai_api_key is not None,
            "anthropic": self.anthropic_api_key is not None,
            "gemini": self.gemini_api_key is not None,
            "ollama": True,
        }
