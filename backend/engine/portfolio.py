"""Multi-asset portfolio backtester — vectorized, reproducible, no look-ahead.

This module sits *alongside* :mod:`engine.backtest` (single-asset). The two
engines are intentionally independent: this one accepts a fixed weight
vector + a rebalance schedule, the other accepts a single-ticker signal
strategy. Both honor the same rigor contract — bar-event execution, no
look-ahead, realistic costs, deterministic results pinned by a run hash.

Architecture
============

Given ``K`` tickers and ``n`` aligned bars, the simulation maintains:

* ``cash`` — scalar dollar balance.
* ``qty`` — vector ``(K,)`` of share counts per ticker.
* ``equity`` — vector ``(n,)``, the public equity curve.

At any bar ``t`` the mark-to-market identity is

    equity[t] = cash + qty @ closes[t, :]                              (1)

and between two consecutive rebalance executions at bars ``e_i`` and
``e_{i+1}``, ``cash`` and ``qty`` are constant, so the entire slice of
the equity curve reduces to a single matrix product:

    equity[e_i : e_{i+1}] = cash + closes[e_i : e_{i+1}, :] @ qty      (2)

That is the core vectorized update — one matmul per *rebalance segment*,
NOT per bar. The only Python-level loop walks rebalance events
(typically <= 12/year for monthly), so the hot path is numpy-bound.

Rebalance triggers and turnover
-------------------------------

A "rebalance trigger" fires at the first trading day of each new
schedule period (month / week / quarter), or every bar for "daily", or
only at bar 0 for "never". Per the QuantSense no-look-ahead contract,
**signals on bar t execute at bar t+1's open**: the trigger observed at
bar ``t`` therefore generates orders that fill at bar ``t+1``'s open
prices (with slippage). The initial allocation follows the same rule —
trigger at bar 0, first fills at bar 1's open. As a consequence
``equity[0] == initial_capital`` (all cash, pre-allocation).

At an execution bar ``e`` the steps are:

    portfolio_value_open = cash + qty @ opens[e, :]                    (3)
    target_qty[k]        = portfolio_value_open * w[k] / opens[e, k]   (4)
    delta[k]             = target_qty[k] - qty[k]                      (5)

For each leg, ``sign(delta[k])`` selects the direction; the fill price
is then ``open * (1 + slip)`` for buys and ``open * (1 - slip)`` for
sells (``slip = slippage_bps / 10_000``). Per-leg commission is
``|delta| * commission_per_share + |delta * fill_price| * commission_pct``.
The cash account absorbs both the slippage haircut and the commission.

Turnover is the sum of ``|delta[k] * fill_price[k]|`` across every leg
of every rebalance (including the initial allocation) — i.e. the dollar
value of all trades. This is what drives transaction-cost drag: every
rebalance moves the portfolio's realized return below its
buy-and-hold-with-perfect-weights counterpart by approximately
``slippage_bps * (turnover / equity)``, plus per-leg commissions.

Why the matrix form is correct
-------------------------------

Equation (2) is just the no-arbitrage MTM identity applied
component-wise: between rebalances no order fills, so each share count
is constant and the only time-varying input is ``closes[t, :]``. The
matmul ``closes @ qty`` produces the per-bar marketed value of the
positions; adding scalar ``cash`` gives the equity. Because ``qty`` and
``cash`` only change at rebalance bars, vectorizing across the
in-segment slice introduces no look-ahead and is byte-identical to a
per-bar Python loop.

The initial allocation costs and slippage land in ``cash`` BEFORE the
first MTM, so equation (2) automatically reflects them in
``equity[1:]``.

Reproducibility
---------------

Run hashing reuses :func:`engine.run_hash.compute_run_hash`, extended to
accept ``Mapping[str, list[OHLCVBar]]`` for the portfolio path. Same
``(bars_by_ticker, config, code_version)`` triple yields the same hash
and a byte-identical equity curve.

Future work (TODO)
------------------

* Dynamic ``weight_strategy: Callable[[Mapping[str, OHLCVBar]],
  dict[str, float]]`` that recomputes target weights at each rebalance
  using a strategy (equal-risk-contribution, momentum-tilted, mean-var,
  ...). Out of scope for this PR — weights are static at config time.
* Fractional-share toggle for institutional realism.
* Cash-drag model when target weights don't sum to 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np

from data.provider import OHLCVBar

from .metrics import PerformanceMetrics, compute_all
from .run_hash import compute_run_hash

RebalanceSchedule = Literal["never", "daily", "weekly", "monthly", "quarterly"]
_VALID_SCHEDULES: tuple[RebalanceSchedule, ...] = (
    "never",
    "daily",
    "weekly",
    "monthly",
    "quarterly",
)
_WEIGHT_TOLERANCE = 1e-6


# ---------------------------------------------------------------------------
# Configuration & result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioBacktestConfig:
    """Frozen config for a multi-asset portfolio backtest.

    ``weights`` ``None`` means equal-weight across ``tickers``. Otherwise
    it must contain exactly one entry per ticker and sum to 1.0 (within
    a small tolerance). All cost knobs (``slippage_bps``,
    ``commission_*``) match the single-asset engine for cross-engine
    comparability.
    """

    tickers: list[str]
    weights: dict[str, float] | None
    start_date: date
    end_date: date
    initial_capital: float = 100_000.0
    rebalance_schedule: RebalanceSchedule = "monthly"
    slippage_bps: float = 5.0
    commission_per_share: float = 0.0
    commission_pct: float = 0.0
    benchmark_ticker: str | None = "SPY"
    seed: int = 42


@dataclass
class PortfolioFillRecord:
    """A single fill leg from initial allocation or a rebalance event."""

    date: date
    ticker: str
    side: str  # "buy" | "sell"
    quantity: float
    fill_price: float
    notional: float  # quantity * fill_price (gross)
    commission: float
    slippage_cost: float  # |qty * open * slip|
    reason: str  # "initial" or "rebalance:<schedule>"


@dataclass
class PortfolioBacktestResult:
    config: PortfolioBacktestConfig
    metrics: PerformanceMetrics
    fills: dict[str, list[PortfolioFillRecord]]
    dates: list[date]
    equity_curve: np.ndarray  # shape (n,), float64
    final_cash: float
    final_positions: dict[str, float]
    total_turnover: float
    per_ticker_pnl: dict[str, dict[str, float]]
    run_hash: str
    benchmark_equity_curve: list[tuple[date, float]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_portfolio_backtest(
    config: PortfolioBacktestConfig,
    bars_by_ticker: Mapping[str, list[OHLCVBar]],
    benchmark_bars: list[OHLCVBar] | None = None,
) -> PortfolioBacktestResult:
    """Run a multi-asset portfolio backtest with the rebalance schedule in ``config``.

    Aligns all per-ticker bar series on the **intersection** of their
    trading dates inside ``[config.start_date, config.end_date]``, so
    every bar is fully populated for every ticker. The initial
    allocation is "triggered" at bar 0 and first executes at bar 1's
    open — preserving the no-look-ahead contract.

    Raises ``ValueError`` for empty / mismatched data and weight
    misconfiguration.
    """
    target_weights = _resolve_target_weights(config)

    # Validate ticker presence and per-ticker data, then align dates.
    aligned_dates, opens, closes = _align_bars(
        config.tickers, bars_by_ticker, config.start_date, config.end_date
    )
    n = len(aligned_dates)
    K = len(config.tickers)

    # Build the canonical run hash on the *raw* per-ticker bars list (not
    # the aligned matrix) so two runs with the same source data hash to
    # the same digest even if start/end clipping is later widened.
    run_hash = compute_run_hash(
        {t: list(bars_by_ticker[t]) for t in config.tickers}, config
    )

    weight_vec = np.array([target_weights[t] for t in config.tickers], dtype=np.float64)

    rebalance_triggers = _rebalance_triggers(aligned_dates, config.rebalance_schedule)

    cash = float(config.initial_capital)
    qty = np.zeros(K, dtype=np.float64)
    equity = np.empty(n, dtype=np.float64)

    fills: dict[str, list[PortfolioFillRecord]] = {t: [] for t in config.tickers}
    cost_basis = np.zeros(K, dtype=np.float64)  # WAC-style $ basis per leg
    realized_pnl = np.zeros(K, dtype=np.float64)
    total_turnover = 0.0

    slip = config.slippage_bps / 10_000.0
    schedule_label = config.rebalance_schedule

    # Walk over rebalance executions. Each `trigger` at bar t produces
    # an execution at bar t+1; we fast-forward equity between consecutive
    # executions with one matmul per segment.
    last_filled_bar = -1  # exclusive: equity[: last_filled_bar + 1] is up to date

    for trigger_bar in rebalance_triggers:
        exec_bar = trigger_bar + 1
        if exec_bar >= n:
            # Last bar's trigger has no next bar to fill on — skip.
            continue

        # MTM the segment [last_filled_bar + 1, exec_bar) using the
        # PRE-rebalance qty / cash (equation 2). On the first iteration
        # this writes equity[0:exec_bar] = initial_capital (qty == 0).
        seg_lo = last_filled_bar + 1
        if exec_bar > seg_lo:
            equity[seg_lo:exec_bar] = cash + closes[seg_lo:exec_bar, :] @ qty

        # Execute the rebalance at exec_bar's open prices.
        cash, qty, cost_basis, realized_pnl, turnover_event = _execute_rebalance(
            exec_bar=exec_bar,
            opens=opens,
            cash=cash,
            qty=qty,
            cost_basis=cost_basis,
            realized_pnl=realized_pnl,
            target_weights=weight_vec,
            tickers=config.tickers,
            commission_per_share=config.commission_per_share,
            commission_pct=config.commission_pct,
            slip=slip,
            fills=fills,
            event_date=aligned_dates[exec_bar],
            reason="initial" if last_filled_bar < 0 else f"rebalance:{schedule_label}",
        )
        total_turnover += turnover_event

        # MTM the execution bar with POST-rebalance qty / cash.
        equity[exec_bar] = cash + closes[exec_bar, :] @ qty
        last_filled_bar = exec_bar

    # Tail: bars after the last execution drift with constant qty/cash.
    if last_filled_bar < 0:
        # Defensive: no execution ever happened (e.g. n == 1). Pure cash.
        equity[:] = cash
    elif last_filled_bar + 1 < n:
        seg_lo = last_filled_bar + 1
        equity[seg_lo:n] = cash + closes[seg_lo:n, :] @ qty

    # ---- Per-ticker realized + unrealized PnL ----------------------------- #
    final_close = closes[n - 1, :] if n > 0 else np.zeros(K)
    unrealized = qty * final_close - cost_basis
    per_ticker_pnl = {
        config.tickers[k]: {
            "realized": float(realized_pnl[k]),
            "unrealized": float(unrealized[k]),
        }
        for k in range(K)
    }

    final_positions = {config.tickers[k]: float(qty[k]) for k in range(K)}

    # ---- Benchmark equity curve aligned to portfolio dates ---------------- #
    bench_curve: list[tuple[date, float]] = []
    if benchmark_bars:
        bench_by_date = {b.date: b.close for b in benchmark_bars}
        first_bench_price: float | None = None
        for bd in aligned_dates:
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
    metrics = compute_all(equity, benchmark_equity=bench_arr)

    return PortfolioBacktestResult(
        config=config,
        metrics=metrics,
        fills=fills,
        dates=list(aligned_dates),
        equity_curve=equity,
        final_cash=float(cash),
        final_positions=final_positions,
        total_turnover=float(total_turnover),
        per_ticker_pnl=per_ticker_pnl,
        run_hash=run_hash,
        benchmark_equity_curve=bench_curve,
    )


# ---------------------------------------------------------------------------
# Validation + alignment helpers
# ---------------------------------------------------------------------------


def _resolve_target_weights(
    config: PortfolioBacktestConfig,
) -> dict[str, float]:
    """Return the validated, ticker-keyed target weights dict.

    ``weights == None`` -> equal weight. Otherwise the dict must have an
    entry per ticker and sum to 1.0 within ``_WEIGHT_TOLERANCE``. Raises
    :class:`ValueError` on any violation.
    """
    if not config.tickers:
        raise ValueError("At least one ticker is required")
    if len(set(config.tickers)) != len(config.tickers):
        raise ValueError("Duplicate tickers in config")

    if config.rebalance_schedule not in _VALID_SCHEDULES:
        raise ValueError(
            f"rebalance_schedule must be one of {_VALID_SCHEDULES}, "
            f"got {config.rebalance_schedule!r}"
        )

    if config.weights is None:
        w = 1.0 / len(config.tickers)
        return dict.fromkeys(config.tickers, w)

    extras = set(config.weights) - set(config.tickers)
    if extras:
        raise ValueError(
            f"weights contain tickers not in config.tickers: {sorted(extras)}"
        )
    missing = set(config.tickers) - set(config.weights)
    if missing:
        raise ValueError(f"weights missing entries for tickers: {sorted(missing)}")

    total = sum(config.weights.values())
    if abs(total - 1.0) > _WEIGHT_TOLERANCE:
        raise ValueError(
            f"weights must sum to 1.0 (got {total:.6f}, tolerance {_WEIGHT_TOLERANCE})"
        )
    return dict(config.weights)


def _align_bars(
    tickers: list[str],
    bars_by_ticker: Mapping[str, list[OHLCVBar]],
    start_date: date,
    end_date: date,
) -> tuple[list[date], np.ndarray, np.ndarray]:
    """Build aligned (n, K) open/close matrices on the intersection of dates.

    Validates that every ticker appears in ``bars_by_ticker`` with at
    least one bar in ``[start_date, end_date]``. Tickers that are
    missing or empty raise :class:`ValueError`. The intersection-based
    alignment guarantees that every bar in the output matrices is fully
    populated for every ticker — no holes, no NaNs.
    """
    if not tickers:
        raise ValueError("At least one ticker is required")

    per_ticker: dict[str, dict[date, OHLCVBar]] = {}
    for ticker in tickers:
        bars = bars_by_ticker.get(ticker)
        if bars is None:
            raise ValueError(f"No bar series provided for ticker {ticker!r}")
        in_range = [b for b in bars if start_date <= b.date <= end_date]
        if not in_range:
            raise ValueError(
                f"Ticker {ticker!r} has no bars in [{start_date}, {end_date}]"
            )
        # Last-write-wins on duplicate dates; OHLCV providers usually
        # already deduplicate but we don't trust callers here.
        per_ticker[ticker] = {b.date: b for b in in_range}

    common_dates: set[date] | None = None
    for ticker in tickers:
        ds = set(per_ticker[ticker].keys())
        common_dates = ds if common_dates is None else common_dates & ds

    assert common_dates is not None  # tickers non-empty
    if len(common_dates) < 2:
        raise ValueError(
            f"Fewer than 2 common trading dates across tickers in "
            f"[{start_date}, {end_date}] — cannot run a backtest"
        )

    aligned = sorted(common_dates)
    n = len(aligned)
    K = len(tickers)
    opens = np.empty((n, K), dtype=np.float64)
    closes = np.empty((n, K), dtype=np.float64)
    for k, ticker in enumerate(tickers):
        idx = per_ticker[ticker]
        for i, d in enumerate(aligned):
            bar = idx[d]
            opens[i, k] = float(bar.open)
            closes[i, k] = float(bar.close)
    return aligned, opens, closes


# ---------------------------------------------------------------------------
# Rebalance schedule
# ---------------------------------------------------------------------------


def _rebalance_triggers(dates: list[date], schedule: RebalanceSchedule) -> list[int]:
    """Return the bar indices at which a rebalance is *triggered*.

    A trigger at bar ``t`` causes orders to fill at the OPEN of bar
    ``t+1`` (no look-ahead — the decision was made on bar ``t``'s
    information set). Bar 0 is always a trigger so the initial
    allocation executes at bar 1's open.

    Schedule semantics — *first-trading-day-of-period* for the periodic
    rebalances:

    * ``never``   — only bar 0.
    * ``daily``   — every bar.
    * ``weekly``  — bar 0 + every bar where the ISO calendar week
                    differs from the previous bar.
    * ``monthly`` — bar 0 + every bar where the calendar month differs
                    from the previous bar (== first trading day of each
                    new month).
    * ``quarterly`` — bar 0 + every bar where ``(year, (month - 1) //
                      3)`` differs from the previous bar (== first
                      trading day of each new calendar quarter).
    """
    n = len(dates)
    if n == 0:
        return []
    if schedule == "never":
        return [0]
    if schedule == "daily":
        return list(range(n))

    triggers: list[int] = [0]
    for i in range(1, n):
        prev, curr = dates[i - 1], dates[i]
        if schedule == "weekly":
            # ISO week: tuple comparison handles year boundaries.
            prev_key = prev.isocalendar()[:2]
            curr_key = curr.isocalendar()[:2]
        elif schedule == "monthly":
            prev_key = (prev.year, prev.month)
            curr_key = (curr.year, curr.month)
        elif schedule == "quarterly":
            prev_key = (prev.year, (prev.month - 1) // 3)
            curr_key = (curr.year, (curr.month - 1) // 3)
        else:  # pragma: no cover — guarded by _resolve_target_weights
            raise ValueError(f"Unknown rebalance schedule: {schedule}")
        if curr_key != prev_key:
            triggers.append(i)
    return triggers


# ---------------------------------------------------------------------------
# Rebalance execution
# ---------------------------------------------------------------------------


def _execute_rebalance(
    *,
    exec_bar: int,
    opens: np.ndarray,
    cash: float,
    qty: np.ndarray,
    cost_basis: np.ndarray,
    realized_pnl: np.ndarray,
    target_weights: np.ndarray,
    tickers: list[str],
    commission_per_share: float,
    commission_pct: float,
    slip: float,
    fills: dict[str, list[PortfolioFillRecord]],
    event_date: date,
    reason: str,
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray, float]:
    """Execute one rebalance event at ``exec_bar``'s open prices.

    Computes target shares from PRE-rebalance portfolio value at the
    open, generates per-leg buy/sell orders, applies slippage +
    commissions to each fill, updates cost basis (weighted-average) and
    realized PnL on sells. Returns the post-rebalance state plus the
    dollar turnover from this event.
    """
    K = len(tickers)
    open_prices = opens[exec_bar, :]
    portfolio_value_open = cash + float(qty @ open_prices)
    if portfolio_value_open <= 0:
        # No capital left; skip the event entirely (positions stay put).
        return cash, qty, cost_basis, realized_pnl, 0.0

    target_qty = portfolio_value_open * target_weights / open_prices
    delta = target_qty - qty

    new_qty = qty.copy()
    new_cost_basis = cost_basis.copy()
    new_realized = realized_pnl.copy()
    new_cash = cash
    turnover_event = 0.0

    for k in range(K):
        d = float(delta[k])
        if d == 0.0:
            continue
        op = float(open_prices[k])
        if d > 0:
            # Buy
            fill_price = op * (1.0 + slip)
            qty_traded = d
            notional = qty_traded * fill_price
            commission = qty_traded * commission_per_share + notional * commission_pct
            slippage_cost = qty_traded * op * slip
            new_cash -= notional + commission
            new_cost_basis[k] += notional + commission
            new_qty[k] = qty[k] + qty_traded
            side = "buy"
        else:
            # Sell
            fill_price = op * (1.0 - slip)
            qty_traded = -d  # positive
            notional = qty_traded * fill_price
            commission = qty_traded * commission_per_share + notional * commission_pct
            slippage_cost = qty_traded * op * slip
            proceeds = notional - commission
            new_cash += proceeds
            # Weighted-avg cost basis: per-share basis stays constant on
            # sells; reduce basis pro-rata then book PnL.
            prev_qty = float(qty[k])
            if prev_qty > 0:
                avg_cost = float(cost_basis[k]) / prev_qty
            else:
                avg_cost = 0.0
            cost_of_sold = avg_cost * qty_traded
            new_cost_basis[k] = cost_basis[k] - cost_of_sold
            new_realized[k] += proceeds - cost_of_sold
            new_qty[k] = qty[k] - qty_traded
            side = "sell"

        turnover_event += notional
        fills[tickers[k]].append(
            PortfolioFillRecord(
                date=event_date,
                ticker=tickers[k],
                side=side,
                quantity=float(qty_traded),
                fill_price=float(fill_price),
                notional=float(notional),
                commission=float(commission),
                slippage_cost=float(slippage_cost),
                reason=reason,
            )
        )

    return new_cash, new_qty, new_cost_basis, new_realized, turnover_event
