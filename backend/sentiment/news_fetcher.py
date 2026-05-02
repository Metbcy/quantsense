from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    headline: str
    snippet: str
    source: str  # "newsapi", "yahoo", "reddit"
    url: str
    published_at: datetime
    ticker: str


class NewsFetcher(ABC):
    @abstractmethod
    async def fetch(self, ticker: str, limit: int = 20) -> list[NewsItem]: ...

    @abstractmethod
    def is_available(self) -> bool: ...


def _safe_parse_dt(value: str | None) -> datetime:
    """Parse an ISO-ish datetime string, falling back to utcnow."""
    if not value:
        return datetime.now(timezone.utc)
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# NewsAPI.org
# ---------------------------------------------------------------------------


class NewsAPIFetcher(NewsFetcher):
    """Fetch headlines from NewsAPI.org /v2/everything."""

    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self) -> None:
        from config.settings import get_settings

        self._api_key = get_settings().newsapi_key

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def fetch(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        if not self.is_available():
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "q": ticker,
                        "sortBy": "publishedAt",
                        "pageSize": min(limit, 100),
                        "language": "en",
                        "apiKey": self._api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            items: list[NewsItem] = []
            for article in data.get("articles", [])[:limit]:
                items.append(
                    NewsItem(
                        headline=article.get("title", "") or "",
                        snippet=article.get("description", "") or "",
                        source="newsapi",
                        url=article.get("url", ""),
                        published_at=_safe_parse_dt(article.get("publishedAt")),
                        ticker=ticker,
                    )
                )
            return items
        except Exception as exc:
            logger.warning("NewsAPIFetcher error for %s: %s", ticker, exc)
            return []


# ---------------------------------------------------------------------------
# Yahoo Finance RSS
# ---------------------------------------------------------------------------


class YahooNewsFetcher(NewsFetcher):
    """Fetch news from yfinance Ticker.news — no API key required."""

    def is_available(self) -> bool:
        return True

    async def fetch(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        try:
            import asyncio
            import yfinance as yf

            t = await asyncio.wait_for(
                asyncio.to_thread(lambda: yf.Ticker(ticker)), timeout=30
            )
            news = await asyncio.wait_for(
                asyncio.to_thread(lambda: t.news), timeout=30
            )
            if not news:
                return []

            items: list[NewsItem] = []
            for article in news[:limit]:
                # yfinance 1.2+ nests data under 'content'
                content = article.get("content", article)
                title = content.get("title", "")
                if not title:
                    continue
                pub_str = content.get("pubDate") or content.get("displayTime") or ""
                pub_dt = _safe_parse_dt(pub_str) if pub_str else datetime.now(timezone.utc)
                summary = content.get("summary", "") or content.get("description", "") or ""
                link = content.get("canonicalUrl", {})
                url = link.get("url", "") if isinstance(link, dict) else str(link)
                items.append(
                    NewsItem(
                        headline=title,
                        snippet=summary[:500],
                        source="yahoo",
                        url=url,
                        published_at=pub_dt,
                        ticker=ticker,
                    )
                )
            return items
        except Exception as exc:
            logger.warning("YahooNewsFetcher error for %s: %s", ticker, exc)
            return []
