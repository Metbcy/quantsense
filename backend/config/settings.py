from functools import lru_cache
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings
from typing import Optional


def _generate_secret() -> str:
    return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./quantsense.db"

    QUANTSENSE_CACHE_DIR: Path = Path.home() / ".quantsense" / "cache" / "ohlcv"
    QUANTSENSE_CACHE_ENABLED: bool = True
    QUANTSENSE_CACHE_FRESHNESS_HOURS: int = 24

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

    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    WEBHOOK_SECRET: str = "quantsense_secret_123"  # Set via env var in production

    PAPER_TRADING_INITIAL_CASH: float = 100000.0
    SENTIMENT_REFRESH_MINUTES: int = 30

    AUTO_TRADE_INTERVAL_MINUTES: int = 30
    AUTO_TRADE_ENABLED: bool = False

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3030,http://127.0.0.1:3030"
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
