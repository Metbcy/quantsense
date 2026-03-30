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
    """Parse Yahoo Finance RSS feed — no API key required."""

    RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

    def is_available(self) -> bool:
        return True

    async def fetch(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        try:
            import feedparser

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(self.RSS_URL.format(ticker=ticker))
                resp.raise_for_status()

            feed = feedparser.parse(resp.text)
            items: list[NewsItem] = []
            for entry in feed.entries[:limit]:
                pub = entry.get("published", "")
                items.append(
                    NewsItem(
                        headline=entry.get("title", ""),
                        snippet=entry.get("summary", ""),
                        source="yahoo",
                        url=entry.get("link", ""),
                        published_at=_safe_parse_dt(pub),
                        ticker=ticker,
                    )
                )
            return items
        except Exception as exc:
            logger.warning("YahooNewsFetcher error for %s: %s", ticker, exc)
            return []


# ---------------------------------------------------------------------------
# Reddit (public JSON API — no auth needed)
# ---------------------------------------------------------------------------


class RedditFetcher(NewsFetcher):
    """Fetch ticker mentions from r/wallstreetbets and r/stocks."""

    SUBREDDITS = ("wallstreetbets", "stocks")
    SEARCH_URL = "https://www.reddit.com/r/{sub}/search.json"
    HEADERS = {"User-Agent": "quantsense-bot/0.1"}

    def is_available(self) -> bool:
        return True

    async def fetch(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        items: list[NewsItem] = []
        per_sub = max(limit // len(self.SUBREDDITS), 5)
        try:
            async with httpx.AsyncClient(timeout=15, headers=self.HEADERS) as client:
                for sub in self.SUBREDDITS:
                    try:
                        resp = await client.get(
                            self.SEARCH_URL.format(sub=sub),
                            params={
                                "q": ticker,
                                "restrict_sr": "on",
                                "sort": "new",
                                "limit": per_sub,
                                "t": "week",
                            },
                        )
                        if resp.status_code == 429:
                            logger.warning(
                                "Reddit rate limited on r/%s, skipping", sub
                            )
                            continue
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as sub_exc:
                        logger.warning(
                            "RedditFetcher error on r/%s: %s", sub, sub_exc
                        )
                        continue

                    for post in data.get("data", {}).get("children", []):
                        pd = post.get("data", {})
                        created = pd.get("created_utc", 0)
                        items.append(
                            NewsItem(
                                headline=pd.get("title", ""),
                                snippet=(pd.get("selftext", "") or "")[:500],
                                source="reddit",
                                url=f"https://reddit.com{pd.get('permalink', '')}",
                                published_at=datetime.fromtimestamp(
                                    created, tz=timezone.utc
                                ),
                                ticker=ticker,
                            )
                        )
        except Exception as exc:
            logger.warning("RedditFetcher error for %s: %s", ticker, exc)

        return items[:limit]
