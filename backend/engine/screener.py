"""Simple stock screener – evaluates multiple tickers in parallel."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta

from data.provider import DataProvider

from .indicators import rsi, sma


@dataclass
class ScreenerResult:
    ticker: str
    price: float
    rsi: float | None
    sma_20: float | None
    sentiment: float | None
    signal: str  # "bullish", "bearish", "neutral"
    score: float  # -1 … +1 composite


async def _screen_one(
    ticker: str,
    provider: DataProvider,
    end: date,
    lookback_days: int = 100,
    sentiment_scores: dict[str, float] | None = None,
) -> ScreenerResult:
    """Evaluate a single ticker and return a ScreenerResult."""
    start = end - timedelta(days=lookback_days)
    bars = await provider.get_ohlcv(ticker, start, end)

    if not bars:
        return ScreenerResult(
            ticker=ticker,
            price=0.0,
            rsi=None,
            sma_20=None,
            sentiment=None,
            signal="neutral",
            score=0.0,
        )

    closes = [b.close for b in bars]
    price = closes[-1]

    rsi_vals = rsi(closes, 14)
    sma_vals = sma(closes, 20)

    current_rsi = rsi_vals[-1]
    current_sma = sma_vals[-1]

    # Use externally-supplied sentiment if available.
    sentiment_val: float | None = None
    if sentiment_scores is not None and ticker in sentiment_scores:
        sentiment_val = sentiment_scores[ticker]

    # Composite score  (-1 … +1).
    score = 0.0
    components = 0

    # RSI component: oversold → positive, overbought → negative.
    if current_rsi is not None:
        rsi_score = (50 - current_rsi) / 50  # maps 0→1, 50→0, 100→-1
        score += rsi_score
        components += 1

    # SMA component: price above SMA → bullish.
    if current_sma is not None and current_sma != 0:
        sma_score = (price - current_sma) / current_sma
        sma_score = max(-1.0, min(1.0, sma_score * 10))  # scale & clamp
        score += sma_score
        components += 1

    # Sentiment component (direct mapping).
    if sentiment_val is not None:
        score += sentiment_val
        components += 1

    if components > 0:
        score /= components

    score = max(-1.0, min(1.0, score))

    # Determine signal label.
    if score > 0.2:
        signal = "bullish"
    elif score < -0.2:
        signal = "bearish"
    else:
        signal = "neutral"

    return ScreenerResult(
        ticker=ticker,
        price=price,
        rsi=current_rsi,
        sma_20=current_sma,
        sentiment=sentiment_val,
        signal=signal,
        score=round(score, 4),
    )


async def screen_tickers(
    tickers: list[str],
    provider: DataProvider,
    sentiment_scores: dict[str, float] | None = None,
) -> list[ScreenerResult]:
    """Screen all *tickers* concurrently and return results sorted by score (desc).

    Parameters
    ----------
    sentiment_scores:
        Optional mapping of ticker → latest sentiment score (-1 … +1).
    """
    end = date.today()
    tasks = [_screen_one(t, provider, end, sentiment_scores=sentiment_scores) for t in tickers]
    results = await asyncio.gather(*tasks)
    return sorted(results, key=lambda r: r.score, reverse=True)
