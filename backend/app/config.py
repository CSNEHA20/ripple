import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    environment: str = "development"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Pre-registered evidence weights & decay half-lives (hours) as specified in Plan v2
    evidence_weights: dict[str, float] = {
        "metric": 3.0,
        "recent_deploy": 2.5,
        "architecture_change": 2.5,
        "dependency_path": 1.5,
        "past_incident": 2.0,
        "decision": 1.0,
        "doc": 1.0,
    }

    evidence_half_lives_hours: dict[str, float | None] = {
        "metric": 1.0,
        "recent_deploy": 6.0,
        "architecture_change": 24.0,
        "dependency_path": None,  # No decay
        "past_incident": 720.0,   # 30 days
        "decision": 2160.0,       # 90 days
        "doc": 2160.0,            # 90 days
    }

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    github_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
