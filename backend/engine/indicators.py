"""Pure-function technical indicators.

Every function returns a list whose length matches the input.  Positions
where there is insufficient data to compute the indicator are filled with
``None``.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Simple Moving Average
# ---------------------------------------------------------------------------

def sma(prices: list[float], period: int) -> list[float | None]:
    """Simple moving average over *period* bars."""
    n = len(prices)
    if period <= 0 or n == 0:
        return [None] * n
    result: list[float | None] = [None] * n
    arr = np.array(prices, dtype=np.float64)
    cumsum = np.cumsum(arr)
    for i in range(period - 1, n):
        if i == period - 1:
            result[i] = float(cumsum[i] / period)
        else:
            result[i] = float((cumsum[i] - cumsum[i - period]) / period)
    return result


# ---------------------------------------------------------------------------
# Exponential Moving Average
# ---------------------------------------------------------------------------

def ema(prices: list[float], period: int) -> list[float | None]:
    """Exponential moving average over *period* bars."""
    n = len(prices)
    if period <= 0 or n == 0:
        return [None] * n
    result: list[float | None] = [None] * n
    multiplier = 2.0 / (period + 1)
    # Seed with the SMA of the first *period* values.
    if n < period:
        return result
    seed = float(np.mean(prices[:period]))
    result[period - 1] = seed
    prev = seed
    for i in range(period, n):
        val = prices[i] * multiplier + prev * (1 - multiplier)
        result[i] = val
        prev = val
    return result


# ---------------------------------------------------------------------------
# Relative Strength Index
# ---------------------------------------------------------------------------

def rsi(prices: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI over *period* bars."""
    n = len(prices)
    if period <= 0 or n < period + 1:
        return [None] * n

    result: list[float | None] = [None] * n
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - 100.0 / (1.0 + rs)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - 100.0 / (1.0 + rs)
    return result


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    prices: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line, signal line, and histogram."""
    n = len(prices)
    fast_ema = ema(prices, fast)
    slow_ema = ema(prices, slow)

    macd_line: list[float | None] = [None] * n
    for i in range(n):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i]

    # Build signal line as EMA of the non-None macd values, then map back.
    macd_vals: list[float] = []
    macd_idx: list[int] = []
    for i, v in enumerate(macd_line):
        if v is not None:
            macd_vals.append(v)
            macd_idx.append(i)

    signal_line: list[float | None] = [None] * n
    histogram: list[float | None] = [None] * n

    if len(macd_vals) >= signal:
        sig_ema = ema(macd_vals, signal)
        for j, idx in enumerate(macd_idx):
            if sig_ema[j] is not None:
                signal_line[idx] = sig_ema[j]
                histogram[idx] = macd_line[idx] - sig_ema[j]  # type: ignore[operator]

    return macd_line, signal_line, histogram


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger_bands(
    prices: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Upper band, middle band (SMA), lower band."""
    n = len(prices)
    middle = sma(prices, period)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n

    arr = np.array(prices, dtype=np.float64)
    for i in range(period - 1, n):
        window = arr[i - period + 1 : i + 1]
        sd = float(np.std(window, ddof=0))
        mid = middle[i]
        if mid is not None:
            upper[i] = mid + std_dev * sd
            lower[i] = mid - std_dev * sd

    return upper, middle, lower


# ---------------------------------------------------------------------------
# Average True Range
# ---------------------------------------------------------------------------

def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """Average True Range over *period* bars."""
    n = len(highs)
    if period <= 0 or n < 2:
        return [None] * n

    result: list[float | None] = [None] * n
    true_ranges: list[float] = [0.0]  # first bar has no previous close
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if n < period + 1:
        return result

    # Initial ATR is the SMA of the first *period* true ranges (skip index 0).
    first_atr = float(np.mean(true_ranges[1 : period + 1]))
    result[period] = first_atr
    prev = first_atr
    for i in range(period + 1, n):
        val = (prev * (period - 1) + true_ranges[i]) / period
        result[i] = val
        prev = val
    return result
