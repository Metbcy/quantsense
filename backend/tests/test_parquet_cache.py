"""Tests for the Parquet-backed OHLCV cache (``data.parquet_cache``)."""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pyarrow.parquet as pq
import pytest

from data.parquet_cache import ParquetOHLCVCache, _SCHEMA
from data.provider import OHLCVBar


def _bar(d: date, close: float = 100.0) -> OHLCVBar:
    return OHLCVBar(
        date=d,
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1_000_000,
    )


def _bars_range(start: date, end: date, base: float = 100.0) -> list[OHLCVBar]:
    out: list[OHLCVBar] = []
    d = start
    i = 0
    while d <= end:
        out.append(_bar(d, base + i * 0.1))
        d += timedelta(days=1)
        i += 1
    return out


class _RecordingFetcher:
    def __init__(self, bars_factory):
        self.calls: list[tuple[str, date, date]] = []
        self._factory = bars_factory

    def __call__(self, ticker: str, start: date, end: date) -> list[OHLCVBar]:
        self.calls.append((ticker, start, end))
        return self._factory(ticker, start, end)


# ---------------------------------------------------------------------- 1
def test_cold_fetch_writes_parquet_with_correct_schema(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(cache_dir=tmp_path)
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))

    start, end = date(2024, 1, 1), date(2024, 1, 10)
    bars = cache.get_or_fetch("AAPL", start, end, fetcher)

    assert len(fetcher.calls) == 1
    assert fetcher.calls[0] == ("AAPL", start, end)
    assert len(bars) == 10
    assert bars[0].date == start
    assert bars[-1].date == end

    parquet_path = tmp_path / "AAPL.parquet"
    assert parquet_path.exists()

    table = pq.read_table(parquet_path)
    assert table.schema.equals(_SCHEMA)
    assert table.num_rows == 10
    assert table.column("date")[0].as_py() == start


# ---------------------------------------------------------------------- 2
def test_warm_fetch_skips_fetcher(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=999_999,  # never stale
    )
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))

    start, end = date(2020, 1, 1), date(2020, 1, 31)
    cache.get_or_fetch("MSFT", start, end, fetcher)
    assert len(fetcher.calls) == 1

    cache.get_or_fetch("MSFT", start, end, fetcher)
    cache.get_or_fetch("MSFT", start, end, fetcher)
    assert len(fetcher.calls) == 1  # still 1: no extra fetches


# ---------------------------------------------------------------------- 3
def test_partial_range_fetches_only_missing(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=999_999,
    )
    # Seed with Jan-Mar
    seed = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("GOOG", date(2023, 1, 1), date(2023, 3, 31), seed)
    assert len(seed.calls) == 1

    # Now ask for Feb-Apr; fetcher should be called once with start=Apr 1.
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    bars = cache.get_or_fetch("GOOG", date(2023, 2, 1), date(2023, 4, 30), fetcher)

    assert len(fetcher.calls) == 1
    _, fs, fe = fetcher.calls[0]
    assert fs == date(2023, 4, 1)
    assert fe == date(2023, 4, 30)

    dates = [b.date for b in bars]
    assert dates[0] == date(2023, 2, 1)
    assert dates[-1] == date(2023, 4, 30)
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)  # no duplicates


# ---------------------------------------------------------------------- 4
def test_atomic_write_failure_leaves_main_file_intact(
    tmp_path: Path,
) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=999_999,
    )
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("AMZN", date(2022, 1, 1), date(2022, 1, 10), fetcher)

    parquet_path = tmp_path / "AMZN.parquet"
    original_bytes = parquet_path.read_bytes()

    # Force os.replace to raise after the temp file has been written.
    with patch("data.parquet_cache.os.replace", side_effect=OSError("simulated")):
        with pytest.raises(OSError):
            cache.get_or_fetch(
                "AMZN",
                date(2022, 2, 1),
                date(2022, 2, 5),
                _RecordingFetcher(lambda t, s, e: _bars_range(s, e)),
            )

    # Main file unchanged.
    assert parquet_path.read_bytes() == original_bytes
    # No leftover .tmp files.
    leftovers = [p for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []


# ---------------------------------------------------------------------- 5
def test_dedup_on_overlap_keeps_no_duplicates(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=999_999,
    )
    # Seed Jan-Mar with base=100.
    cache.get_or_fetch(
        "AAPL",
        date(2024, 1, 1),
        date(2024, 3, 31),
        _RecordingFetcher(lambda t, s, e: _bars_range(s, e, base=100.0)),
    )

    # Force a refetch path by deleting cache awareness of dates we re-deliver:
    # Simulate by directly merging an overlapping batch via a fetcher that
    # returns Feb-Apr with base=200.
    overlap_fetcher = _RecordingFetcher(
        lambda t, s, e: _bars_range(date(2024, 2, 1), date(2024, 4, 30), base=200.0)
    )
    cache.get_or_fetch("AAPL", date(2024, 4, 1), date(2024, 4, 30), overlap_fetcher)

    table = pq.read_table(tmp_path / "AAPL.parquet")
    dates = table.column("date").to_pylist()
    closes = table.column("close").to_pylist()

    assert len(dates) == len(set(dates))  # unique dates
    assert dates == sorted(dates)
    assert dates[0] == date(2024, 1, 1)
    assert dates[-1] == date(2024, 4, 30)

    # Newer data wins on overlap: Feb-Mar should now reflect base=200.
    feb1_idx = dates.index(date(2024, 2, 1))
    assert closes[feb1_idx] >= 200.0


# ---------------------------------------------------------------------- 6
def test_sort_on_append_with_out_of_order_fetch(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=999_999,
    )

    def shuffled(t, s, e):
        bars = _bars_range(s, e)
        # Reverse so fetcher returns newest-first.
        return list(reversed(bars))

    cache.get_or_fetch(
        "TSLA", date(2024, 6, 1), date(2024, 6, 15), _RecordingFetcher(shuffled)
    )

    table = pq.read_table(tmp_path / "TSLA.parquet")
    dates = table.column("date").to_pylist()
    assert dates == sorted(dates)
    assert dates[0] == date(2024, 6, 1)
    assert dates[-1] == date(2024, 6, 15)


# ---------------------------------------------------------------------- 7
def test_clear_removes_single_ticker_and_all(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(cache_dir=tmp_path, freshness_hours=999_999)
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    for tk in ("AAA", "BBB", "CCC"):
        cache.get_or_fetch(tk, date(2024, 1, 1), date(2024, 1, 5), fetcher)

    assert (tmp_path / "AAA.parquet").exists()
    assert (tmp_path / "BBB.parquet").exists()
    assert (tmp_path / "CCC.parquet").exists()

    cache.clear("BBB")
    assert (tmp_path / "AAA.parquet").exists()
    assert not (tmp_path / "BBB.parquet").exists()
    assert (tmp_path / "CCC.parquet").exists()

    cache.clear(None)
    assert list(tmp_path.glob("*.parquet")) == []


# ---------------------------------------------------------------------- 8
def test_has_coverage_returns_false_when_outside_envelope(
    tmp_path: Path,
) -> None:
    cache = ParquetOHLCVCache(cache_dir=tmp_path, freshness_hours=999_999)
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("NVDA", date(2024, 5, 1), date(2024, 5, 31), fetcher)

    # Fully covered.
    assert cache.has_coverage("NVDA", date(2024, 5, 1), date(2024, 5, 31))
    assert cache.has_coverage("NVDA", date(2024, 5, 10), date(2024, 5, 20))

    # Leading gap.
    assert not cache.has_coverage("NVDA", date(2024, 4, 30), date(2024, 5, 31))
    # Trailing gap.
    assert not cache.has_coverage("NVDA", date(2024, 5, 1), date(2024, 6, 1))

    # Unknown ticker → False.
    assert not cache.has_coverage("UNKNOWN", date(2024, 5, 1), date(2024, 5, 5))


# ---------------------------------------------------------------------- 9
def test_disabled_cache_is_a_no_op(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(cache_dir=None)
    assert cache.enabled is False

    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    bars = cache.get_or_fetch("META", date(2024, 1, 1), date(2024, 1, 5), fetcher)
    assert len(bars) == 5

    # Subsequent call: fetcher invoked again (no caching).
    cache.get_or_fetch("META", date(2024, 1, 1), date(2024, 1, 5), fetcher)
    assert len(fetcher.calls) == 2

    # No parquet files written anywhere under tmp_path.
    assert list(tmp_path.glob("*.parquet")) == []

    stats = cache.stats()
    assert stats["enabled"] is False
    assert stats["total_bars"] == 0


# ---------------------------------------------------------------------- 10
def test_freshness_refetches_recent_tail_when_mtime_is_stale(
    tmp_path: Path,
) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=24,
        freshness_lookback_days=3,
    )
    today = date.today()
    start = today - timedelta(days=20)

    seed = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("SPY", start, today, seed)
    assert len(seed.calls) == 1

    parquet_path = tmp_path / "SPY.parquet"
    assert parquet_path.exists()

    # Age the file by 48h so it's stale.
    stale_mtime = time.time() - 48 * 3600
    os.utime(parquet_path, (stale_mtime, stale_mtime))

    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("SPY", start, today, fetcher)

    # One tail-refetch call, scoped to the lookback window.
    assert len(fetcher.calls) == 1
    _, fs, fe = fetcher.calls[0]
    assert fs == today - timedelta(days=cache.freshness_lookback_days)
    assert fe == today


def test_freshness_does_not_refetch_when_fresh(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(
        cache_dir=tmp_path,
        freshness_hours=24,
        freshness_lookback_days=3,
    )
    today = date.today()
    start = today - timedelta(days=20)

    seed = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("QQQ", start, today, seed)

    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("QQQ", start, today, fetcher)

    # Cache is fresh (mtime ~ now) so no extra fetches.
    assert len(fetcher.calls) == 0


def test_stats_reports_cached_tickers_and_bars(tmp_path: Path) -> None:
    cache = ParquetOHLCVCache(cache_dir=tmp_path, freshness_hours=999_999)
    fetcher = _RecordingFetcher(lambda t, s, e: _bars_range(s, e))
    cache.get_or_fetch("AAA", date(2024, 1, 1), date(2024, 1, 10), fetcher)
    cache.get_or_fetch("BBB", date(2024, 1, 1), date(2024, 1, 5), fetcher)

    stats = cache.stats()
    assert stats["enabled"] is True
    assert stats["cache_dir"] == str(tmp_path)
    assert sorted(stats["cached_tickers"]) == ["AAA", "BBB"]
    assert stats["total_bars"] == 15
