from functools import lru_cache

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./quantsense.db"

    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    NEWSAPI_KEY: Optional[str] = None
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    ALPACA_API_KEY: Optional[str] = None
    ALPACA_SECRET_KEY: Optional[str] = None
    ALPACA_PAPER: bool = True

    WEBHOOK_SECRET: str = "quantsense_secret_123"

    PAPER_TRADING_INITIAL_CASH: float = 100000.0
    SENTIMENT_REFRESH_MINUTES: int = 30

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3030"
    RATE_LIMIT: str = "60/minute"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def groq_api_key(self) -> str:
        return self.GROQ_API_KEY or ""

    @property
    def openai_api_key(self) -> str:
        return self.OPENAI_API_KEY or ""

    @property
    def newsapi_key(self) -> str:
        return self.NEWSAPI_KEY or ""

    @property
    def reddit_client_id(self) -> str:
        return self.REDDIT_CLIENT_ID or ""

    @property
    def reddit_client_secret(self) -> str:
        return self.REDDIT_CLIENT_SECRET or ""


settings = Settings()


@lru_cache
def get_settings() -> Settings:
    return Settings()
