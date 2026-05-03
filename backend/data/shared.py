"""Shared cached data provider instance.

Import ``provider`` from this module instead of instantiating
YahooFinanceProvider directly — this ensures a single cache is
shared across all API routes.

Two cache layers stack here, in order:

1. :class:`ParquetOHLCVCache` (durable, on-disk, per-ticker Parquet files).
   Survives process restarts. Used to avoid re-fetching the same historical
   bars across walk-forward / optimisation runs.
2. :class:`CachedDataProvider` (in-process TTL cache). Absorbs
   high-frequency duplicate calls within a single API session.

Wiring is driven entirely by settings (``QUANTSENSE_CACHE_ENABLED`` /
``QUANTSENSE_CACHE_DIR`` / ``QUANTSENSE_CACHE_FRESHNESS_HOURS``) so it
can be toggled in tests / dev without code changes.
"""

from config.settings import settings
from data.cache import CachedDataProvider
from data.parquet_cache import ParquetOHLCVCache
from data.yahoo_provider import YahooFinanceProvider


def _build_parquet_cache() -> ParquetOHLCVCache | None:
    if not settings.QUANTSENSE_CACHE_ENABLED:
        return None
    return ParquetOHLCVCache(
        cache_dir=settings.QUANTSENSE_CACHE_DIR,
        freshness_hours=settings.QUANTSENSE_CACHE_FRESHNESS_HOURS,
    )


parquet_cache = _build_parquet_cache()
provider = CachedDataProvider(YahooFinanceProvider(cache=parquet_cache))
