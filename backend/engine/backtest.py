"""Backtest runner — bar-event-driven simulator with realistic execution.

Key design points:

  * **No look-ahead bias**: a signal generated using bars[0..t] executes at
    bars[t+1].open. The legacy "signal at close, fill at same close" model
    is gone.
  * **Slippage** is modeled as a configurable basis-point haircut applied to
    the next-bar open in the direction of the trade.
  * **Commission** supports both percentage of notional and per-share fixed
    cost (configurable at the same time).
  * **Position sizing** is fixed-fraction of equity at signal time.
  * **Risk overlays** (stop-loss, take-profit, ATR stop) are evaluated
    intra-bar against the bar's high/low, NOT the close — fills happen at
    the trigger price plus slippage.

Metrics come from `engine.metrics.compute_all`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from data.provider import OHLCVBar

from .indicators import atr
from .metrics import PerformanceMetrics, compute_all
from .strategy import Signal, SignalType, Strategy


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
    commission_pct: float = 0.0          # fraction of notional, e.g. 0.001
    commission_per_share: float = 0.0    # absolute $ per share
    slippage_bps: float = 1.0            # 1 bp = 0.01%
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
    # Per-bar series for downstream stats / charts
    benchmark_equity_curve: list[tuple[date, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal position tracker
# ---------------------------------------------------------------------------

@dataclass
class _Position:
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    peak_price: float = 0.0
    atr_stop_price: float | None = None


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
    """Execute a full backtest and return results with metrics.

    Args:
        config: BacktestConfig.
        bars: full OHLCV history for the ticker (will be filtered by date).
        sentiment_scores: aligned with `bars` if provided.
        benchmark_bars: optional benchmark (e.g. SPY) — aligned by date for
            alpha/beta computation.
        n_trials: number of strategy variants this result was selected from
            (used by the Deflated Sharpe Ratio). Pass the grid size when
            reporting an optimized strategy.
    """
    # Filter bars to the configured date range.
    filtered_bars = [b for b in bars if config.start_date <= b.date <= config.end_date]
    if len(filtered_bars) < 2:
        return _empty_result(config)

    # Align sentiment scores with filtered bars if provided.
    sentiment: list[float] | None = None
    if sentiment_scores is not None:
        bar_dates = {b.date: idx for idx, b in enumerate(bars)}
        sentiment = []
        for fb in filtered_bars:
            orig_idx = bar_dates.get(fb.date)
            if orig_idx is not None and orig_idx < len(sentiment_scores):
                sentiment.append(sentiment_scores[orig_idx])
            else:
                sentiment.append(0.0)

    signals = config.strategy.generate_signals(filtered_bars, sentiment)

    # Pre-calculate ATR if needed (uses full history to avoid edge effects).
    atr_filtered: list[float | None] = [None] * len(filtered_bars)
    if config.atr_stop_multiplier is not None:
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
                atr_filtered[idx] = all_atrs[orig_idx]

    cash = config.initial_capital
    pos = _Position()
    trades: list[BacktestTradeRecord] = []
    equity_curve: list[tuple[date, float]] = []

    slip = config.slippage_bps / 10_000.0  # bps -> fraction

    # We iterate through bars but execute at bar i+1's open.
    # Pending order from the previous bar's close-of-day decision:
    pending_signal: Signal | None = None

    for i, bar in enumerate(filtered_bars):
        # ---- Execute any order pending from yesterday's signal ----
        if pending_signal is not None:
            exec_price = bar.open
            if pending_signal.type == SignalType.BUY and pos.quantity == 0:
                fill_price = exec_price * (1 + slip)
                cash = _open_long(
                    cash=cash,
                    pos=pos,
                    config=config,
                    bar=bar,
                    fill_price=fill_price,
                    trades=trades,
                    reason=pending_signal.reason or "Strategy buy",
                )
            elif pending_signal.type == SignalType.SELL and pos.quantity > 0:
                fill_price = exec_price * (1 - slip)
                cash = _close_long(
                    cash, pos, config, bar, fill_price, trades,
                    reason=pending_signal.reason or "Strategy sell",
                )
            pending_signal = None

        # ---- Intra-bar risk overlays (use bar's high/low) ----
        if pos.quantity > 0:
            triggered_price: float | None = None
            triggered_reason = ""
            # Stop-loss vs trailing peak (uses bar low)
            if config.stop_loss_pct is not None:
                stop_price = pos.peak_price * (1 - config.stop_loss_pct)
                if bar.low <= stop_price:
                    triggered_price = min(stop_price, bar.open)
                    triggered_reason = "Stop-loss"
            # ATR stop
            if pos.atr_stop_price is not None and bar.low <= pos.atr_stop_price:
                cand = min(pos.atr_stop_price, bar.open)
                if triggered_price is None or cand < triggered_price:
                    triggered_price = cand
                    triggered_reason = "ATR stop"
            # Take-profit (uses bar high)
            if config.take_profit_pct is not None:
                target = pos.avg_entry_price * (1 + config.take_profit_pct)
                if bar.high >= target:
                    cand = max(target, bar.open)
                    if triggered_price is None or cand > triggered_price:
                        triggered_price = cand
                        triggered_reason = "Take-profit"
            if triggered_price is not None:
                fill_price = triggered_price * (1 - slip)
                cash = _close_long(
                    cash, pos, config, bar, fill_price, trades,
                    reason=triggered_reason,
                )
            else:
                # Update trailing peak using bar high.
                if bar.high > pos.peak_price:
                    pos.peak_price = bar.high

        # ---- Generate signal at end of bar; queue for next bar's open ----
        sig = signals[i] if i < len(signals) else Signal(SignalType.HOLD, 0.0, "")
        if sig.type in (SignalType.BUY, SignalType.SELL):
            pending_signal = sig

        # Mark-to-market with close.
        equity_curve.append((bar.date, cash + pos.quantity * bar.close))

        # Set ATR stop on entry (after fill above).
        if (
            pos.quantity > 0
            and pos.atr_stop_price is None
            and config.atr_stop_multiplier is not None
            and atr_filtered[i] is not None
        ):
            pos.atr_stop_price = pos.avg_entry_price - (
                atr_filtered[i] * config.atr_stop_multiplier
            )

    # Force-close any open position at the final close (no look-ahead — this
    # is end-of-data, not a forward fill).
    if pos.quantity > 0 and equity_curve:
        last_bar = filtered_bars[-1]
        cash = _close_long(
            cash, pos, config, last_bar, last_bar.close * (1 - slip),
            trades, reason="End of backtest",
        )
        equity_curve[-1] = (last_bar.date, cash)

    # ---- Benchmark equity curve aligned to backtest dates ----
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
            bench_curve.append(
                (bd, config.initial_capital * price / first_bench_price)
            )

    # ---- Compute metrics ----
    equity_arr = np.array([v for _, v in equity_curve], dtype=np.float64)
    bench_arr = (
        np.array([v for _, v in bench_curve], dtype=np.float64)
        if bench_curve
        else None
    )
    metrics = compute_all(equity_arr, benchmark_equity=bench_arr, n_trials=n_trials)

    return BacktestResult(
        config=config,
        metrics=metrics,
        trades=trades,
        equity_curve=equity_curve,
        benchmark_equity_curve=bench_curve,
    )


# ---------------------------------------------------------------------------
# Trade helpers
# ---------------------------------------------------------------------------

def _open_long(
    *,
    cash: float,
    pos: _Position,
    config: BacktestConfig,
    bar: OHLCVBar,
    fill_price: float,
    trades: list,
    reason: str,
) -> float:
    """Open a long. Mutates `pos`; returns updated cash."""
    if fill_price <= 0:
        return cash
    available = cash * config.position_size_pct
    if available <= 0:
        return cash
    denom = fill_price * (1 + config.commission_pct) + config.commission_per_share
    if denom <= 0:
        return cash
    qty = available / denom
    if qty <= 0:
        return cash
    notional = qty * fill_price
    commission = notional * config.commission_pct + qty * config.commission_per_share
    cost = notional + commission
    new_cash = cash - cost
    pos.quantity = qty
    pos.avg_entry_price = fill_price
    pos.peak_price = fill_price
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
    return new_cash


def _close_long(
    cash: float,
    pos: _Position,
    config: BacktestConfig,
    bar: OHLCVBar,
    fill_price: float,
    trades: list,
    reason: str,
) -> float:
    qty = pos.quantity
    notional = qty * fill_price
    commission = notional * config.commission_pct + qty * config.commission_per_share
    proceeds = notional - commission
    pnl = proceeds - qty * pos.avg_entry_price
    new_cash = cash + proceeds
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
    pos.quantity = 0.0
    pos.avg_entry_price = 0.0
    pos.peak_price = 0.0
    pos.atr_stop_price = None
    return new_cash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_result(config: BacktestConfig) -> BacktestResult:
    metrics = compute_all(np.array([], dtype=np.float64))
    return BacktestResult(
        config=config, metrics=metrics, trades=[], equity_curve=[]
    )


# ---------------------------------------------------------------------------
# Backwards-compat shim
# ---------------------------------------------------------------------------

# The old code exported a `BacktestMetrics` dataclass with a fixed shape; map
# attribute access through to the new PerformanceMetrics so legacy callers and
# serializers don't blow up. We expose the new type under both names.

BacktestMetrics = PerformanceMetrics
