"""Parquet-backed OHLCV cache for time-series bars.

Storage layout
--------------
One Parquet file per ticker:  ``<cache_dir>/<TICKER>.parquet``

Schema (Arrow):
  - ``date``    date32[day]  (unique key)
  - ``open``    float64
  - ``high``    float64
  - ``low``     float64
  - ``close``   float64
  - ``volume``  int64

Bars are kept sorted by ``date`` ascending and deduplicated by date on
append; when an incoming bar collides with an existing bar, the new
bar wins (so a same-day re-fetch can correct an unsettled close).

Atomic writes
-------------
Writes go to ``<TICKER>.parquet.tmp.<pid>.<rand>`` then ``os.replace``
(atomic rename on POSIX/Linux and Windows). On any failure the temp
file is removed and the main file is left untouched.

Cache invalidation / freshness
------------------------------
``get_or_fetch`` only fetches the date ranges that are NOT already
covered by the cache. In addition, when the requested ``end`` date is
"recent" (>= today - 1 day) AND the cache file's mtime is older than
``freshness_hours``, the trailing ``freshness_lookback_days`` of the
window are re-fetched even if already cached. This handles the case
where yfinance has not yet published "today's" bar at first fetch but
has by the next request.

Disabled mode
-------------
Passing ``cache_dir=None`` instantiates a no-op cache: ``get_or_fetch``
always invokes the fetcher and never writes a file. This keeps the
disable-flag plumbing trivial at the call site.
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from data.provider import OHLCVBar

logger = logging.getLogger(__name__)


_SCHEMA = pa.schema(
    [
        pa.field("date", pa.date32()),
        pa.field("open", pa.float64()),
        pa.field("high", pa.float64()),
        pa.field("low", pa.float64()),
        pa.field("close", pa.float64()),
        pa.field("volume", pa.int64()),
    ]
)


def _safe_ticker(ticker: str) -> str:
    """Sanitize a ticker for use as a filename."""
    safe = "".join(c for c in ticker.upper() if c.isalnum() or c in ("-", "_", "."))
    if not safe:
        raise ValueError(f"Invalid ticker for cache filename: {ticker!r}")
    return safe


def _bars_to_table(bars: list[OHLCVBar]) -> pa.Table:
    return pa.table(
        {
            "date": pa.array([b.date for b in bars], type=pa.date32()),
            "open": pa.array([float(b.open) for b in bars], type=pa.float64()),
            "high": pa.array([float(b.high) for b in bars], type=pa.float64()),
            "low": pa.array([float(b.low) for b in bars], type=pa.float64()),
            "close": pa.array([float(b.close) for b in bars], type=pa.float64()),
            "volume": pa.array([int(b.volume) for b in bars], type=pa.int64()),
        },
        schema=_SCHEMA,
    )


def _table_to_bars(table: pa.Table) -> list[OHLCVBar]:
    cols = {
        "date": table.column("date").to_pylist(),
        "open": table.column("open").to_pylist(),
        "high": table.column("high").to_pylist(),
        "low": table.column("low").to_pylist(),
        "close": table.column("close").to_pylist(),
        "volume": table.column("volume").to_pylist(),
    }
    return [
        OHLCVBar(
            date=cols["date"][i],
            open=cols["open"][i],
            high=cols["high"][i],
            low=cols["low"][i],
            close=cols["close"][i],
            volume=cols["volume"][i],
        )
        for i in range(table.num_rows)
    ]


class ParquetOHLCVCache:
    """Local Parquet-on-disk cache for OHLCV bars.

    See module docstring for storage layout and freshness semantics.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        freshness_hours: int = 24,
        freshness_lookback_days: int = 5,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.enabled = self.cache_dir is not None
        self.freshness_hours = int(freshness_hours)
        self.freshness_lookback_days = int(freshness_lookback_days)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths
    def _path(self, ticker: str) -> Path:
        assert self.cache_dir is not None
        return self.cache_dir / f"{_safe_ticker(ticker)}.parquet"

    def _lock_for(self, ticker: str) -> threading.Lock:
        key = _safe_ticker(ticker)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    # --------------------------------------------------------------- read/write
    def _read_table(self, ticker: str) -> pa.Table | None:
        if not self.enabled:
            return None
        path = self._path(ticker)
        if not path.exists():
            return None
        try:
            return pq.read_table(path, schema=_SCHEMA)
        except Exception as exc:  # corrupt file
            logger.warning("Failed to read parquet cache %s: %s", path, exc)
            return None

    def _atomic_write_table(self, ticker: str, table: pa.Table) -> None:
        path = self._path(ticker)
        tmp = path.with_suffix(f".parquet.tmp.{os.getpid()}.{secrets.token_hex(4)}")
        try:
            pq.write_table(table, tmp)
            os.replace(tmp, path)
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise

    # -------------------------------------------------------------- merge core
    @staticmethod
    def _merge_sort_dedup(existing: pa.Table | None, new: pa.Table) -> pa.Table:
        """Concat existing + new, dedup by date (new wins), sort ascending."""
        if existing is None or existing.num_rows == 0:
            combined = new
        elif new.num_rows == 0:
            combined = existing
        else:
            new_dates = pa.array(new.column("date").to_pylist(), type=pa.date32())
            mask = pc.invert(pc.is_in(existing.column("date"), value_set=new_dates))
            filtered_existing = existing.filter(mask)
            combined = pa.concat_tables([filtered_existing, new])

        if combined.num_rows == 0:
            return combined.cast(_SCHEMA) if combined.schema != _SCHEMA else combined

        indices = pc.sort_indices(combined, sort_keys=[("date", "ascending")])
        return combined.take(indices)

    @staticmethod
    def _slice_table(table: pa.Table, start: date, end: date) -> pa.Table:
        if table.num_rows == 0:
            return table
        col = table.column("date")
        ge = pc.greater_equal(col, pa.scalar(start, type=pa.date32()))
        le = pc.less_equal(col, pa.scalar(end, type=pa.date32()))
        return table.filter(pc.and_(ge, le))

    # ------------------------------------------------------------- public API
    def has_coverage(self, ticker: str, start: date, end: date) -> bool:
        """Return True iff the cache covers the entire ``[start, end]`` span.

        "Covers" here means the cached date range's [min, max] envelope
        contains [start, end]. Trading-day gaps inside the envelope are
        considered cached (the cache stores trading days only).
        """
        if not self.enabled:
            return False
        table = self._read_table(ticker)
        if table is None or table.num_rows == 0:
            return False
        cached_min = table.column("date")[0].as_py()
        cached_max = table.column("date")[-1].as_py()
        return cached_min <= start and cached_max >= end

    def get_or_fetch(
        self,
        ticker: str,
        start: date,
        end: date,
        fetcher: Callable[[str, date, date], list[OHLCVBar]],
    ) -> list[OHLCVBar]:
        """Return bars in ``[start, end]`` for ``ticker``.

        Missing ranges are pulled via ``fetcher(ticker, fetch_start, fetch_end)``
        and merged into the cache. Returns the requested slice, sorted
        ascending and deduped.

        When disabled (``cache_dir=None``), this is equivalent to calling
        ``fetcher(ticker, start, end)`` directly without touching disk.
        """
        if not self.enabled:
            bars = fetcher(ticker, start, end)
            return sorted(bars, key=lambda b: b.date)

        if start > end:
            return []

        with self._lock_for(ticker):
            existing = self._read_table(ticker)
            fetch_ranges = self._compute_fetch_ranges(ticker, existing, start, end)

            new_bars: list[OHLCVBar] = []
            for fs, fe in fetch_ranges:
                if fs > fe:
                    continue
                fetched = fetcher(ticker, fs, fe)
                if fetched:
                    new_bars.extend(fetched)

            if new_bars:
                new_table = _bars_to_table(new_bars)
                merged = self._merge_sort_dedup(existing, new_table)
                self._atomic_write_table(ticker, merged)
                final = merged
            else:
                final = existing if existing is not None else _bars_to_table([])

            sliced = self._slice_table(final, start, end)
            return _table_to_bars(sliced)

    def _compute_fetch_ranges(
        self,
        ticker: str,
        existing: pa.Table | None,
        start: date,
        end: date,
    ) -> list[tuple[date, date]]:
        """Determine which sub-ranges still need to be fetched.

        Strategy:
        - No cache → fetch [start, end].
        - Leading gap (start < cached_min) → fetch [start, cached_min - 1d].
        - Trailing gap (end > cached_max) → fetch [cached_max + 1d, end].
        - Recent end + stale mtime → also re-fetch the trailing
          ``freshness_lookback_days`` of the window to catch a late-published
          most-recent bar.
        """
        if existing is None or existing.num_rows == 0:
            return [(start, end)]

        cached_min: date = existing.column("date")[0].as_py()
        cached_max: date = existing.column("date")[-1].as_py()

        ranges: list[tuple[date, date]] = []
        if start < cached_min:
            ranges.append((start, min(end, cached_min - timedelta(days=1))))
        if end > cached_max:
            ranges.append((max(start, cached_max + timedelta(days=1)), end))

        today = date.today()
        if end >= today - timedelta(days=1) and self._is_stale(ticker):
            tail_start = max(start, end - timedelta(days=self.freshness_lookback_days))
            ranges.append((tail_start, end))

        return _coalesce_ranges(ranges)

    def _is_stale(self, ticker: str) -> bool:
        if not self.enabled:
            return True
        path = self._path(ticker)
        if not path.exists():
            return True
        mtime = path.stat().st_mtime
        age_seconds = datetime.now().timestamp() - mtime
        return age_seconds > self.freshness_hours * 3600

    # ----------------------------------------------------------------- admin
    def clear(self, ticker: str | None = None) -> None:
        """Remove a single ticker's parquet (``ticker``) or all of them (``None``)."""
        if not self.enabled:
            return
        if ticker is not None:
            path = self._path(ticker)
            if path.exists():
                path.unlink()
            return
        for path in self.cache_dir.glob("*.parquet"):
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Failed to clear cache file %s: %s", path, exc)

    def stats(self) -> dict:
        """Return a snapshot dict useful for debugging / logging."""
        if not self.enabled:
            return {
                "cache_dir": None,
                "enabled": False,
                "cached_tickers": [],
                "total_bars": 0,
            }
        tickers: list[str] = []
        total = 0
        for path in sorted(self.cache_dir.glob("*.parquet")):
            tickers.append(path.stem)
            try:
                total += pq.read_metadata(path).num_rows
            except Exception:
                pass
        return {
            "cache_dir": str(self.cache_dir),
            "enabled": True,
            "cached_tickers": tickers,
            "total_bars": total,
        }


def _coalesce_ranges(
    ranges: list[tuple[date, date]],
) -> list[tuple[date, date]]:
    """Merge overlapping / touching date ranges and drop empty ones."""
    valid = [(s, e) for s, e in ranges if s <= e]
    if not valid:
        return []
    valid.sort(key=lambda r: r[0])
    out: list[tuple[date, date]] = [valid[0]]
    for s, e in valid[1:]:
        last_s, last_e = out[-1]
        if s <= last_e + timedelta(days=1):
            out[-1] = (last_s, max(last_e, e))
        else:
            out.append((s, e))
    return out
