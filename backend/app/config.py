from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    environment: str = "development"
    cors_origins: Any = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("cors_origins", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json
            if v.startswith("["):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(x) for x in v]
        return ["*"]

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

    # Hypothesis sufficiency thresholds (M5)
    min_supporting_evidence_count: int = 2
    min_margin_threshold: float = 0.5
    max_unresolved_contradiction: float = 2.0

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    nemotron_api_key: str | None = None
    nvidia_api_key: str | None = None
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    llm_provider: str | None = None
    embeddings_backend: str = "semantic"
    github_token: str | None = None
    github_repo: str | None = None
    data_dir: str = "data"
    webhook_secret: str | None = None
    webhook_token: str | None = None
    slack_webhook_url: str | None = None
    prometheus_url: str = "http://localhost:9090"
    telemetry_source: str = "simulator"
    api_key_header: str = "X-API-Key"
    auth_dev_mode: bool = False
    api_keys_seed_file: str = "data/api_keys_seed.json"
    verification_window_seconds: float = 60.0
    verification_poll_step_seconds: float = 10.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
