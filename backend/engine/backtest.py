"""Backtest runner — vectorized bar-event simulator with realistic execution.

Key design points:

  * **No look-ahead bias**: a signal generated using bars[0..t] executes at
    bars[t+1].open. Encoded explicitly at the array level as
    ``pending = sig_type[:-1]`` so future readers cannot accidentally
    re-introduce look-ahead by indexing the wrong way.
  * **Slippage** is a configurable basis-point haircut applied to the
    fill price in the direction of the trade.
  * **Commissions** support both percentage of notional and per-share fixed
    cost (configurable simultaneously).
  * **Position sizing** is fixed-fraction of equity at signal time.
  * **Risk overlays** (stop-loss, take-profit, ATR stop) are evaluated
    intra-bar against bar high/low — fills happen at the trigger price
    plus slippage. Trailing peak (used by the percentage stop-loss) is
    cumulative on bar highs since entry, expressed via
    ``np.maximum.accumulate`` rather than a Python loop.

Algorithm:

  The simulation has only two states (flat / long) and at most one entry
  and one exit per trade. Instead of a per-bar Python loop we walk
  *trade-by-trade*:

    1. From the current cursor, find the next BUY-pending bar with a
       single ``np.where`` on the pre-built ``pending`` array.
    2. Compute the entry fill, then build masks for all four possible
       exit triggers (stop-loss, ATR stop, take-profit, pending SELL)
       across the rest of the array, and locate the first ``True`` with
       ``np.argmax``.
    3. Mark-to-market the in-position slice with vectorized
       ``cash + qty * close[e:j]`` arithmetic.
    4. Advance the cursor and repeat.

  Because every per-bar arithmetic is numpy, the only Python-level work
  scales with the number of trades, not the number of bars.

Metrics come from `engine.metrics.compute_all`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from data.provider import OHLCVBar

from .indicators import atr
from .metrics import PerformanceMetrics, compute_all
from .strategy import SignalType, Strategy


# ---------------------------------------------------------------------------
# Configuration & result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    ticker: str
    strategy: Strategy
    start_date: date
    end_date: date
    initial_capital: float = 100_000.0
    # Costs
    commission_pct: float = 0.0  # fraction of notional, e.g. 0.001
    commission_per_share: float = 0.0  # absolute $ per share
    slippage_bps: float = 1.0  # 1 bp = 0.01%
    # Sizing
    position_size_pct: float = 0.95
    # Risk overlays
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    atr_stop_multiplier: float | None = None


@dataclass
class BacktestTradeRecord:
    date: date
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    value: float
    commission: float
    slippage_cost: float
    pnl: float  # 0 for buys, realised P&L net of costs for sells
    reason: str = ""


@dataclass
class BacktestResult:
    config: BacktestConfig
    metrics: PerformanceMetrics
    trades: list[BacktestTradeRecord]
    equity_curve: list[tuple[date, float]]
    benchmark_equity_curve: list[tuple[date, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_backtest(
    config: BacktestConfig,
    bars: list[OHLCVBar],
    sentiment_scores: list[float] | None = None,
    benchmark_bars: list[OHLCVBar] | None = None,
    n_trials: int = 1,
) -> BacktestResult:
    """Execute a vectorized backtest and return results with metrics.

    Behavior is byte-identical to the prior loop-based implementation:
    same fills, same equity curve, same metrics. See module docstring for
    the algorithm.
    """
    filtered_bars = [b for b in bars if config.start_date <= b.date <= config.end_date]
    if len(filtered_bars) < 2:
        return _empty_result(config)

    n = len(filtered_bars)
    sentiment = _align_sentiment(bars, filtered_bars, sentiment_scores)
    signals = config.strategy.generate_signals(filtered_bars, sentiment)

    atr_filtered = _align_atr(bars, filtered_bars, config)

    # ---- Vectorize OHLC and signal arrays --------------------------------- #
    # `closes` is always needed for mark-to-market and force-close; `opens`
    # is needed for entry/exit fills. `highs`/`lows` are only consulted when
    # at least one risk overlay is configured — defer their construction.
    has_overlay = (
        config.stop_loss_pct is not None
        or config.take_profit_pct is not None
        or config.atr_stop_multiplier is not None
    )
    opens = np.fromiter((b.open for b in filtered_bars), dtype=np.float64, count=n)
    closes = np.fromiter((b.close for b in filtered_bars), dtype=np.float64, count=n)
    if has_overlay:
        highs = np.fromiter((b.high for b in filtered_bars), dtype=np.float64, count=n)
        lows = np.fromiter((b.low for b in filtered_bars), dtype=np.float64, count=n)
    else:
        highs = closes  # placeholder, never inspected on the fast path
        lows = closes

    # Encode signal types: +1=BUY, -1=SELL, 0=HOLD.
    sig_type = np.zeros(n, dtype=np.int8)
    for i, s in enumerate(signals):
        if s.type == SignalType.BUY:
            sig_type[i] = 1
        elif s.type == SignalType.SELL:
            sig_type[i] = -1

    # Pending order at bar j is the signal generated at bar j-1
    # (next-bar-open execution; this is the explicit "no look-ahead" contract).
    pending = np.zeros(n, dtype=np.int8)
    pending[1:] = sig_type[:-1]

    # Precompute lookup tables: ``next_buy[k]`` is the smallest index i >= k
    # with pending[i] == 1, or n if there is none. Likewise for next_sell.
    # Built right-to-left in one O(n) pass so the per-trade entry/exit search
    # is a constant-time array lookup instead of a shrinking ``np.flatnonzero``.
    next_buy = _build_next_index(pending == 1, n)
    next_sell = _build_next_index(pending == -1, n)

    # ---- Simulation state ------------------------------------------------- #
    cash = float(config.initial_capital)
    slip = config.slippage_bps / 10_000.0
    trades: list[BacktestTradeRecord] = []
    equity = np.empty(n, dtype=np.float64)

    cursor = 0  # bar index from which we look for the next entry

    while cursor < n:
        # ---- Find next entry: smallest e >= cursor with pending == BUY ---- #
        e = next_buy[cursor]
        if e >= n:
            equity[cursor:n] = cash
            break

        if e > cursor:
            equity[cursor:e] = cash  # flat bars MTM at cash

        # ---- Try to open at bar e ---------------------------------------- #
        opened = _try_open_long(
            cash=cash,
            config=config,
            bar=filtered_bars[e],
            open_price=float(opens[e]),
            slip=slip,
            reason=signals[e - 1].reason or "Strategy buy",
            trades=trades,
        )
        if opened is None:
            # Open failed silently (insufficient cash, fill_price <= 0, ...).
            # Mark this bar at cash and advance one step; the next pending
            # signal (sig_type[e]) is already encoded at pending[e+1].
            equity[e] = cash
            cursor = e + 1
            continue

        cash_after_buy, qty, fill_price = opened
        avg_entry = fill_price

        # ATR stop level is established at the END of the entry bar; the
        # entry bar's risk-overlay check therefore must NOT see it.
        atr_stop_price: float | None = None
        if config.atr_stop_multiplier is not None and atr_filtered[e] is not None:
            atr_stop_price = avg_entry - atr_filtered[e] * config.atr_stop_multiplier

        # ---- Locate the exit bar via pure-numpy masks -------------------- #
        j, exit_kind, exit_price, exit_reason = _find_exit_bar(
            e=e,
            n=n,
            opens=opens,
            highs=highs,
            lows=lows,
            pending=pending,
            next_sell=next_sell,
            avg_entry=avg_entry,
            atr_stop_price=atr_stop_price,
            stop_loss_pct=config.stop_loss_pct,
            take_profit_pct=config.take_profit_pct,
            slip=slip,
            signals=signals,
        )

        if j is None:
            # Position runs to the last bar with no trigger. Mark-to-market
            # in-position slice, then force-close at the final close.
            equity[e:n] = cash_after_buy + qty * closes[e:n]
            last_bar = filtered_bars[n - 1]
            cash = _record_close(
                cash_after_buy=cash_after_buy,
                qty=qty,
                avg_entry=avg_entry,
                fill_price=float(closes[n - 1]) * (1 - slip),
                config=config,
                bar=last_bar,
                slip=slip,
                reason="End of backtest",
                trades=trades,
            )
            equity[n - 1] = cash
            break

        # In-position MTM for [e, j-1] — vectorized.
        if j > e:
            equity[e:j] = cash_after_buy + qty * closes[e:j]

        cash = _record_close(
            cash_after_buy=cash_after_buy,
            qty=qty,
            avg_entry=avg_entry,
            fill_price=exit_price,
            config=config,
            bar=filtered_bars[j],
            slip=slip,
            reason=exit_reason,
            trades=trades,
        )
        equity[j] = cash  # exit bar MTM = post-close cash, qty is now 0
        cursor = j + 1

    # ---- Build the public-facing equity curve ----------------------------- #
    equity_curve: list[tuple[date, float]] = [
        (filtered_bars[k].date, float(equity[k])) for k in range(n)
    ]

    # ---- Benchmark equity curve aligned to backtest dates ----------------- #
    bench_curve: list[tuple[date, float]] = []
    if benchmark_bars:
        bench_by_date = {b.date: b.close for b in benchmark_bars}
        first_bench_price: float | None = None
        for bd, _ in equity_curve:
            price = bench_by_date.get(bd)
            if price is None:
                continue
            if first_bench_price is None:
                first_bench_price = price
            bench_curve.append((bd, config.initial_capital * price / first_bench_price))

    # ---- Metrics ---------------------------------------------------------- #
    bench_arr = (
        np.array([v for _, v in bench_curve], dtype=np.float64) if bench_curve else None
    )
    metrics = compute_all(equity, benchmark_equity=bench_arr, n_trials=n_trials)

    return BacktestResult(
        config=config,
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
        benchmark_equity_curve=bench_curve,
    )


# ---------------------------------------------------------------------------
# Exit-bar search (vectorized over the in-position slice)
# ---------------------------------------------------------------------------


def _find_exit_bar(
    *,
    e: int,
    n: int,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    pending: np.ndarray,
    next_sell: np.ndarray,
    avg_entry: float,
    atr_stop_price: float | None,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
    slip: float,
    signals: list,
) -> tuple[int | None, str, float, str]:
    """Locate the first bar j in [e, n) at which the long position must close.

    Returns ``(j, kind, exit_price, reason)`` where ``kind`` is one of
    ``"sell"`` (pending strategy SELL) or ``"risk"`` (overlay trigger), and
    ``exit_price`` is already adjusted for slippage. If no exit triggers
    before bar n-1 (inclusive), returns ``(None, "", 0.0, "")`` and the
    caller force-closes at the final bar's close.

    Fast-path: when no risk overlay is configured the exit is just the next
    pending SELL signal — one ``next_sell`` table lookup, O(1).

    Slow-path (any overlay set): build SL / ATR / TP / SELL trigger masks
    over the in-position slice and take the first ``True``. The peak price
    used by the trailing percentage stop-loss is the cumulative max of bar
    highs *prior to* the bar being checked, with the entry's fill price as
    the seed. We construct this with ``np.maximum.accumulate`` on a shifted
    array — no Python loop.
    """
    seg_len = n - e  # placeholder; redefined inside the slow path if entered
    has_overlay = (
        stop_loss_pct is not None
        or atr_stop_price is not None
        or take_profit_pct is not None
    )

    # ---- Fast path: only strategy SELL signals can close the position --- #
    if not has_overlay:
        # At bar e the pending slot held the BUY that just executed — start
        # the SELL search at e+1.
        j = int(next_sell[e + 1]) if e + 1 < n else n
        if j >= n:
            return None, "", 0.0, ""
        exit_price = float(opens[j]) * (1.0 - slip)
        reason = signals[j - 1].reason or "Strategy sell"
        return j, "sell", exit_price, reason

    # ---- Slow path: build trigger masks over the in-position slice ------ #
    # Cap the slice length at the next pending SELL (which is itself an exit
    # candidate). Anything past that bar can't be the first exit, so there's
    # no value scanning highs/lows there.
    sell_j = int(next_sell[e + 1]) if e + 1 < n else n
    end = min(sell_j + 1, n)  # +1 so that index sell_j is included
    seg_len = end - e
    rng = slice(e, end)

    sl_trigger = np.zeros(seg_len, dtype=bool)
    sl_price_arr: np.ndarray | None = None
    if stop_loss_pct is not None:
        # peak_for_check[k] is the trailing peak as seen at the START of bar
        # (e+k):
        #   k = 0: just entered, peak = avg_entry
        #   k > 0: max(avg_entry, max(highs[e..e+k-1]))
        peak_for_check = np.empty(seg_len, dtype=np.float64)
        peak_for_check[0] = avg_entry
        if seg_len > 1:
            cummax_high = np.maximum.accumulate(highs[e : end - 1])
            peak_for_check[1:] = np.maximum(avg_entry, cummax_high)
        sl_price_arr = peak_for_check * (1.0 - stop_loss_pct)
        sl_trigger = lows[rng] <= sl_price_arr

    atr_trigger = np.zeros(seg_len, dtype=bool)
    if atr_stop_price is not None:
        atr_trigger = lows[rng] <= atr_stop_price
        atr_trigger[0] = False  # ATR stop only activates from bar e+1 onward

    tp_trigger = np.zeros(seg_len, dtype=bool)
    tp_target = (
        avg_entry * (1.0 + take_profit_pct) if take_profit_pct is not None else None
    )
    if tp_target is not None:
        tp_trigger = highs[rng] >= tp_target

    sell_pending = pending[rng] == -1
    sell_pending[0] = False

    any_exit = sl_trigger | atr_trigger | tp_trigger | sell_pending
    if not any_exit.any():
        return None, "", 0.0, ""

    rel = int(np.argmax(any_exit))
    j = e + rel

    # Pending SELL at bar j is consumed at the open BEFORE the intra-bar
    # risk overlays would fire — strategy signals therefore have priority.
    if sell_pending[rel]:
        exit_price = float(opens[j]) * (1.0 - slip)
        reason = signals[j - 1].reason or "Strategy sell"
        return j, "sell", exit_price, reason

    # Risk overlay: original priority chain is SL → ATR → TP. Each step can
    # *replace* the running candidate based on direction (cheaper for stops,
    # higher for take-profit). This priority chain matches the legacy code
    # exactly (preserving the documented quirk that TP wins when both SL
    # and TP fire on the same bar).
    triggered_price: float | None = None
    triggered_reason = ""
    if stop_loss_pct is not None and bool(sl_trigger[rel]):
        stop_price = float(sl_price_arr[rel])  # type: ignore[index]
        triggered_price = min(stop_price, float(opens[j]))
        triggered_reason = "Stop-loss"
    if atr_stop_price is not None and bool(atr_trigger[rel]):
        cand = min(atr_stop_price, float(opens[j]))
        if triggered_price is None or cand < triggered_price:
            triggered_price = cand
            triggered_reason = "ATR stop"
    if tp_target is not None and bool(tp_trigger[rel]):
        cand = max(tp_target, float(opens[j]))
        if triggered_price is None or cand > triggered_price:
            triggered_price = cand
            triggered_reason = "Take-profit"

    assert triggered_price is not None, "any_exit was True but no trigger resolved"
    exit_price = triggered_price * (1.0 - slip)
    return j, "risk", exit_price, triggered_reason


# ---------------------------------------------------------------------------
# Trade-record helpers
# ---------------------------------------------------------------------------


def _try_open_long(
    *,
    cash: float,
    config: BacktestConfig,
    bar: OHLCVBar,
    open_price: float,
    slip: float,
    reason: str,
    trades: list,
) -> tuple[float, float, float] | None:
    """Try to open a long at ``open_price`` adjusted for slippage.

    Returns ``(cash_after, qty, fill_price)`` on success or ``None`` if any
    of the fail-safes trip (matches the original ``_open_long`` no-op
    semantics exactly).
    """
    fill_price = open_price * (1.0 + slip)
    if fill_price <= 0:
        return None
    available = cash * config.position_size_pct
    if available <= 0:
        return None
    denom = fill_price * (1.0 + config.commission_pct) + config.commission_per_share
    if denom <= 0:
        return None
    qty = available / denom
    if qty <= 0:
        return None

    notional = qty * fill_price
    commission = notional * config.commission_pct + qty * config.commission_per_share
    cost = notional + commission
    cash_after = cash - cost

    trades.append(
        BacktestTradeRecord(
            date=bar.date,
            side="buy",
            price=fill_price,
            quantity=qty,
            value=notional,
            commission=commission,
            slippage_cost=qty * fill_price * (config.slippage_bps / 10_000.0),
            pnl=0.0,
            reason=reason,
        )
    )
    return cash_after, qty, fill_price


def _record_close(
    *,
    cash_after_buy: float,
    qty: float,
    avg_entry: float,
    fill_price: float,
    config: BacktestConfig,
    bar: OHLCVBar,
    slip: float,
    reason: str,
    trades: list,
) -> float:
    """Close the long and append a sell trade record. Returns post-close cash."""
    notional = qty * fill_price
    commission = notional * config.commission_pct + qty * config.commission_per_share
    proceeds = notional - commission
    pnl = proceeds - qty * avg_entry
    trades.append(
        BacktestTradeRecord(
            date=bar.date,
            side="sell",
            price=fill_price,
            quantity=qty,
            value=notional,
            commission=commission,
            slippage_cost=qty * fill_price * (config.slippage_bps / 10_000.0),
            pnl=pnl,
            reason=reason,
        )
    )
    return cash_after_buy + proceeds


# ---------------------------------------------------------------------------
# Sentiment / ATR alignment helpers
# ---------------------------------------------------------------------------


def _build_next_index(mask: np.ndarray, n: int) -> np.ndarray:
    """Return ``out`` of length n+1 where ``out[k]`` is the smallest index
    i >= k such that ``mask[i]`` is True, or ``n`` if no such i exists.

    Built with a single right-to-left ``np.minimum.accumulate``-style pass
    over an int array, then a final O(n) Python copy is avoided by taking
    a reversed view — the entire build is linear and allocation-light.
    """
    # Place the index value at every True position; n at every False position.
    # Then a reverse cumulative-min gives "next True at-or-after k".
    idx = np.where(mask, np.arange(n, dtype=np.int64), n)
    # Reverse, take running min, reverse back.
    rev = idx[::-1]
    rev_min = np.minimum.accumulate(rev)
    nxt = rev_min[::-1].copy()
    # Append a sentinel at index n so callers can safely index with k+1.
    out = np.empty(n + 1, dtype=np.int64)
    out[:n] = nxt
    out[n] = n
    return out


def _align_sentiment(
    bars: list[OHLCVBar],
    filtered_bars: list[OHLCVBar],
    sentiment_scores: list[float] | None,
) -> list[float] | None:
    if sentiment_scores is None:
        return None
    bar_dates = {b.date: idx for idx, b in enumerate(bars)}
    out: list[float] = []
    for fb in filtered_bars:
        orig_idx = bar_dates.get(fb.date)
        if orig_idx is not None and orig_idx < len(sentiment_scores):
            out.append(sentiment_scores[orig_idx])
        else:
            out.append(0.0)
    return out


def _align_atr(
    bars: list[OHLCVBar],
    filtered_bars: list[OHLCVBar],
    config: BacktestConfig,
) -> list[float | None]:
    out: list[float | None] = [None] * len(filtered_bars)
    if config.atr_stop_multiplier is None:
        return out
    all_atrs = atr(
        [b.high for b in bars],
        [b.low for b in bars],
        [b.close for b in bars],
        period=14,
    )
    bar_dates = {b.date: idx for idx, b in enumerate(bars)}
    for idx, fb in enumerate(filtered_bars):
        orig_idx = bar_dates.get(fb.date)
        if orig_idx is not None:
            out[idx] = all_atrs[orig_idx]
    return out


# ---------------------------------------------------------------------------
# Empty-result helper
# ---------------------------------------------------------------------------


def _empty_result(config: BacktestConfig) -> BacktestResult:
    metrics = compute_all(np.array([], dtype=np.float64))
    return BacktestResult(config=config, metrics=metrics, trades=[], equity_curve=[])


# ---------------------------------------------------------------------------
# Backwards-compat shim
# ---------------------------------------------------------------------------

# The old code exported a `BacktestMetrics` dataclass with a fixed shape; map
# attribute access through to the new PerformanceMetrics so legacy callers and
# serializers don't blow up. We expose the new type under both names.

BacktestMetrics = PerformanceMetrics
