"""Application configuration and settings validation."""

from __future__ import annotations

from functools import lru_cache

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """QuantMind runtime settings."""

    app_name: str = "QuantMind"
    debug: bool = Field(default=False)

    # API auth
    api_key: str | None = Field(default=None, alias="QUANTMIND_API_KEY")
    require_auth: bool = Field(default=False, alias="QUANTMIND_REQUIRE_AUTH")

    # Rate limiting (requests per minute per client)
    rate_limit_per_minute: int = Field(default=60, alias="QUANTMIND_RATE_LIMIT_PER_MINUTE")

    # Risk controls
    max_order_quantity: float = Field(default=10_000.0, alias="QUANTMIND_MAX_ORDER_QUANTITY")
    max_daily_loss_pct: float = Field(default=5.0, alias="QUANTMIND_MAX_DAILY_LOSS_PCT")
    allowed_products: str = Field(default="CNC", alias="QUANTMIND_ALLOWED_PRODUCTS")

    # Audit
    audit_db_path: str = Field(default="audit.db", alias="QUANTMIND_AUDIT_DB_PATH")

    # Upstox
    upstox_api_key: str | None = Field(default=None, alias="UPSTOX_API_KEY")
    upstox_access_token: str | None = Field(default=None, alias="UPSTOX_ACCESS_TOKEN")
    upstox_analytics_token: str | None = Field(default=None, alias="UPSTOX_ANALYTICS_TOKEN")

    # LLM
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # Agent
    auto_approve: bool = Field(default=False, alias="QUANTMIND_AUTO_APPROVE")
    max_agent_turns: int = Field(default=5, alias="QUANTMIND_MAX_AGENT_TURNS")

    model_config = ConfigDict(env_prefix="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
