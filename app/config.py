from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Investment Evaluation Report API"
    xai_api_key: str | None = None
    xai_model: str = "grok-4-1-fast-non-reasoning"
    sec_user_agent: str = "InvestmentEvaluator/0.1 your-email@example.com"
    request_timeout_seconds: float = 20.0
    news_lookback_days: int = 90
    max_news_items: int = 8
    max_analyzed_sources: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
