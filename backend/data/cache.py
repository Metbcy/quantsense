"""In-memory TTL cache for market data."""

import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from data.provider import DataProvider, OHLCVBar, Quote, TickerInfo

logger = logging.getLogger(__name__)

DEFAULT_QUOTE_TTL = 60  # seconds
DEFAULT_OHLCV_TTL = 300  # 5 minutes — OHLCV changes less frequently
DEFAULT_SEARCH_TTL = 600  # 10 minutes


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class CachedDataProvider(DataProvider):
    """Wraps another DataProvider with a time-based in-memory cache."""

    def __init__(
        self,
        provider: DataProvider,
        quote_ttl: int = DEFAULT_QUOTE_TTL,
        ohlcv_ttl: int = DEFAULT_OHLCV_TTL,
        search_ttl: int = DEFAULT_SEARCH_TTL,
    ) -> None:
        self._provider = provider
        self._quote_ttl = quote_ttl
        self._ohlcv_ttl = ohlcv_ttl
        self._search_ttl = search_ttl
        self._cache: dict[str, _CacheEntry] = {}

    def _get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.value

    def _put(self, key: str, value: Any, ttl: int) -> None:
        self._cache[key] = _CacheEntry(value=value, expires_at=time.monotonic() + ttl)

    def clear(self) -> None:
        self._cache.clear()

    def evict(self, ticker: str) -> None:
        """Remove all cached entries for a specific ticker."""
        keys_to_remove = [k for k in self._cache if k.startswith(f"quote:{ticker}:") or
                          k.startswith(f"ohlcv:{ticker}:") or k.startswith(f"search:{ticker}:")]
        for k in keys_to_remove:
            del self._cache[k]

    @property
    def stats(self) -> dict[str, int]:
        """Return cache size and number of expired entries (for monitoring)."""
        now = time.monotonic()
        total = len(self._cache)
        expired = sum(1 for e in self._cache.values() if now > e.expires_at)
        return {"total": total, "expired": expired, "active": total - expired}

    async def get_quote(self, ticker: str) -> Quote:
        key = f"quote:{ticker}"
        cached = self._get(key)
        if cached is not None:
            logger.debug("Cache hit: %s", key)
            return cached
        result = await self._provider.get_quote(ticker)
        self._put(key, result, self._quote_ttl)
        return result

    async def get_ohlcv(
        self, ticker: str, start: date, end: date, interval: str = "1d"
    ) -> list[OHLCVBar]:
        key = f"ohlcv:{ticker}:{start}:{end}:{interval}"
        cached = self._get(key)
        if cached is not None:
            logger.debug("Cache hit: %s", key)
            return cached
        result = await self._provider.get_ohlcv(ticker, start, end, interval)
        self._put(key, result, self._ohlcv_ttl)
        return result

    async def search_ticker(self, query: str) -> list[TickerInfo]:
        key = f"search:{query}"
        cached = self._get(key)
        if cached is not None:
            logger.debug("Cache hit: %s", key)
            return cached
        result = await self._provider.search_ticker(query)
        self._put(key, result, self._search_ttl)
        return result
