"""Backtest runner – simulates a strategy over historical bars."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

from data.provider import OHLCVBar

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
    commission_pct: float = 0.0
    position_size_pct: float = 0.95
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None


@dataclass
class BacktestMetrics:
    initial_capital: float
    final_value: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    avg_trade_pnl: float
    best_trade_pnl: float
    worst_trade_pnl: float
    profit_factor: float


@dataclass
class BacktestTradeRecord:
    date: date
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    value: float
    pnl: float  # 0 for buys, realised P&L for sells


@dataclass
class BacktestResult:
    config: BacktestConfig
    metrics: BacktestMetrics
    trades: list[BacktestTradeRecord]
    equity_curve: list[tuple[date, float]]


# ---------------------------------------------------------------------------
# Internal position tracker
# ---------------------------------------------------------------------------

@dataclass
class _Position:
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    peak_price: float = 0.0  # for trailing stop


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_backtest(
    config: BacktestConfig,
    bars: list[OHLCVBar],
    sentiment_scores: list[float] | None = None,
) -> BacktestResult:
    """Execute a full backtest and return results with metrics."""

    # Filter bars to the configured date range.
    filtered_bars = [b for b in bars if config.start_date <= b.date <= config.end_date]
    if not filtered_bars:
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

    cash = config.initial_capital
    pos = _Position()
    trades: list[BacktestTradeRecord] = []
    equity_curve: list[tuple[date, float]] = []

    for i, bar in enumerate(filtered_bars):
        price = bar.close
        signal = signals[i] if i < len(signals) else Signal(SignalType.HOLD, 0.0, "")

        # --- stop-loss / take-profit checks (before new signal) ---
        if pos.quantity > 0:
            if config.stop_loss_pct is not None:
                stop_price = pos.peak_price * (1 - config.stop_loss_pct)
                if price <= stop_price:
                    signal = Signal(SignalType.SELL, 1.0, "Stop-loss triggered")

            if config.take_profit_pct is not None:
                target = pos.avg_entry_price * (1 + config.take_profit_pct)
                if price >= target:
                    signal = Signal(SignalType.SELL, 1.0, "Take-profit triggered")

            # Track peak for trailing stop.
            if price > pos.peak_price:
                pos.peak_price = price

        # --- execute signal ---
        if signal.type == SignalType.BUY and pos.quantity == 0:
            available = cash * config.position_size_pct
            commission = available * config.commission_pct
            investable = available - commission
            if investable > 0 and price > 0:
                qty = investable / price
                cost = qty * price + commission
                cash -= cost
                pos.quantity = qty
                pos.avg_entry_price = price
                pos.peak_price = price
                trades.append(
                    BacktestTradeRecord(
                        date=bar.date,
                        side="buy",
                        price=price,
                        quantity=qty,
                        value=qty * price,
                        pnl=0.0,
                    )
                )

        elif signal.type == SignalType.SELL and pos.quantity > 0:
            proceeds = pos.quantity * price
            commission = proceeds * config.commission_pct
            net = proceeds - commission
            pnl = net - pos.quantity * pos.avg_entry_price
            cash += net
            trades.append(
                BacktestTradeRecord(
                    date=bar.date,
                    side="sell",
                    price=price,
                    quantity=pos.quantity,
                    value=proceeds,
                    pnl=pnl,
                )
            )
            pos.quantity = 0.0
            pos.avg_entry_price = 0.0
            pos.peak_price = 0.0

        # Portfolio value = cash + position mark-to-market.
        portfolio_value = cash + pos.quantity * price
        equity_curve.append((bar.date, portfolio_value))

    metrics = _compute_metrics(config, trades, equity_curve)
    return BacktestResult(
        config=config, metrics=metrics, trades=trades, equity_curve=equity_curve
    )


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_metrics(
    config: BacktestConfig,
    trades: list[BacktestTradeRecord],
    equity_curve: list[tuple[date, float]],
) -> BacktestMetrics:
    initial = config.initial_capital
    final = equity_curve[-1][1] if equity_curve else initial
    total_return = ((final - initial) / initial) * 100.0 if initial else 0.0

    # Trade-level stats.
    sell_pnls = [t.pnl for t in trades if t.side == "sell"]
    total_trades = len(sell_pnls)
    wins = [p for p in sell_pnls if p > 0]
    losses = [p for p in sell_pnls if p <= 0]
    win_rate = len(wins) / total_trades * 100.0 if total_trades else 0.0
    avg_pnl = float(np.mean(sell_pnls)) if sell_pnls else 0.0
    best_pnl = max(sell_pnls) if sell_pnls else 0.0
    worst_pnl = min(sell_pnls) if sell_pnls else 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0

    # Sharpe ratio (annualised, 252 trading days).
    values = np.array([v for _, v in equity_curve], dtype=np.float64)
    if len(values) > 1:
        daily_returns = np.diff(values) / values[:-1]
        mean_ret = float(np.mean(daily_returns))
        std_ret = float(np.std(daily_returns, ddof=1))
        sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown.
    max_dd = 0.0
    if len(values) > 0:
        peak = values[0]
        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

    return BacktestMetrics(
        initial_capital=initial,
        final_value=final,
        total_return_pct=total_return,
        sharpe_ratio=sharpe,
        max_drawdown_pct=max_dd,
        win_rate=win_rate,
        total_trades=total_trades,
        avg_trade_pnl=avg_pnl,
        best_trade_pnl=best_pnl,
        worst_trade_pnl=worst_pnl,
        profit_factor=profit_factor,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_result(config: BacktestConfig) -> BacktestResult:
    metrics = BacktestMetrics(
        initial_capital=config.initial_capital,
        final_value=config.initial_capital,
        total_return_pct=0.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        total_trades=0,
        avg_trade_pnl=0.0,
        best_trade_pnl=0.0,
        worst_trade_pnl=0.0,
        profit_factor=0.0,
    )
    return BacktestResult(config=config, metrics=metrics, trades=[], equity_curve=[])
