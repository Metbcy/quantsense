"""Tests for the new quant-grade modules: metrics, walk-forward, significance."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

from data.provider import OHLCVBar
from engine.backtest import BacktestConfig, run_backtest
from engine.metrics import (
    compute_all,
    deflated_sharpe_ratio,
    sharpe_ratio,
    sortino_ratio,
)
from engine.significance import (
    bootstrap_sharpe_block,
    bootstrap_sharpe_ci,
    permutation_test_sharpe,
    returns_from_equity,
)
from engine.strategy import MomentumStrategy
from engine.walk_forward import run_walk_forward


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def test_sharpe_zero_returns():
    rets = np.zeros(20)
    assert sharpe_ratio(rets) == 0.0


def test_sharpe_constant_positive_returns():
    rets = np.full(252, 0.001)
    s = sharpe_ratio(rets)
    # Constant returns -> infinite or huge Sharpe; we cap at finite or expect huge
    assert s == 0.0 or s > 100  # std=0 case returns 0 by convention


def test_sortino_only_punishes_downside():
    # Same mean, different downside: more-downside should have worse Sortino
    a = np.array([0.01, 0.01, 0.01, -0.005, 0.01])
    b = np.array([0.01, 0.01, 0.01, -0.02, 0.025])  # bigger downside, same-ish mean
    assert sortino_ratio(b) < sortino_ratio(a)


def test_deflated_sharpe_lower_with_more_trials():
    rets = np.random.default_rng(0).normal(0.001, 0.01, 252)
    sr = sharpe_ratio(rets)
    dsr_1 = deflated_sharpe_ratio(sr, len(rets), n_trials=1)
    dsr_50 = deflated_sharpe_ratio(sr, len(rets), n_trials=50)
    assert dsr_50 <= dsr_1  # more trials -> stricter penalty


def test_compute_all_smoke():
    eq = 100_000 + np.cumsum(np.random.default_rng(1).normal(50, 200, 252))
    m = compute_all(eq, n_trials=1)
    assert isinstance(m.sharpe_ratio, float)
    assert isinstance(m.sortino_ratio, float)
    assert isinstance(m.calmar_ratio, float)
    assert m.max_drawdown_pct >= 0  # stored as positive percent
    assert m.max_drawdown_duration_bars >= 0


# --------------------------------------------------------------------------- #
# Significance
# --------------------------------------------------------------------------- #
def test_bootstrap_ci_brackets_point_estimate():
    rets = np.random.default_rng(7).normal(0.001, 0.01, 252)
    ci = bootstrap_sharpe_ci(rets, n_resamples=500)
    assert ci.ci_low <= ci.point_estimate <= ci.ci_high


def test_block_bootstrap_ci_brackets_point_estimate():
    rets = np.random.default_rng(7).normal(0.001, 0.01, 252)
    ci = bootstrap_sharpe_block(rets, n_resamples=500)
    assert ci.ci_low <= ci.point_estimate <= ci.ci_high
    assert ci.avg_block_length >= 1.0
    assert ci.n_resamples == 500
    assert ci.confidence == 0.95


def test_block_bootstrap_wider_for_autocorrelated_returns():
    """On strongly autocorrelated returns the block bootstrap should
    produce a noticeably wider CI than the i.i.d. bootstrap, because the
    i.i.d. version under-states the variance of the Sharpe estimator.

    We construct an AR(1) series with phi=0.4 — well within the regime
    where Politis-White picks a block length > 1.
    """
    rng = np.random.default_rng(123)
    n = 500
    phi = 0.4
    eps = rng.normal(0.0005, 0.01, n)
    rets = np.empty(n)
    rets[0] = eps[0]
    for i in range(1, n):
        rets[i] = phi * rets[i - 1] + eps[i]

    iid = bootstrap_sharpe_ci(rets, n_resamples=1000)
    block = bootstrap_sharpe_block(rets, n_resamples=1000)

    iid_width = iid.ci_high - iid.ci_low
    block_width = block.ci_high - block.ci_low
    assert block_width > iid_width, (
        f"Expected block CI wider than i.i.d. CI for AR(1) returns; "
        f"got iid={iid_width:.4f}, block={block_width:.4f}"
    )
    # Politis-White should pick a block length materially > 1 here
    assert block.avg_block_length > 1.5


def test_block_bootstrap_explicit_block_length():
    rets = np.random.default_rng(1).normal(0.001, 0.01, 200)
    ci = bootstrap_sharpe_block(rets, n_resamples=200, block_length=10.0)
    assert ci.avg_block_length == 10.0


def test_block_bootstrap_too_few_observations():
    with pytest.raises(ValueError):
        bootstrap_sharpe_block(np.array([0.01, -0.01]))


def test_permutation_test_random_returns_high_pvalue():
    # Pure i.i.d. noise should have p ~ 0.5, definitely not significant
    rets = np.random.default_rng(42).normal(0, 0.01, 252)
    perm = permutation_test_sharpe(rets, n_permutations=500)
    assert 0.05 < perm.p_value < 0.95


def test_returns_from_equity_basic():
    eq = np.array([100, 110, 121])
    rets = returns_from_equity(eq)
    assert len(rets) == 2
    assert math.isclose(rets[0], 0.1, rel_tol=1e-9)
    assert math.isclose(rets[1], 0.1, rel_tol=1e-9)


# --------------------------------------------------------------------------- #
# Look-ahead bias regression
# --------------------------------------------------------------------------- #
def _bars_from_prices(prices: list[float]) -> list[OHLCVBar]:
    start = date(2024, 1, 1)
    return [
        OHLCVBar(
            date=start + timedelta(days=i),
            open=p,
            high=p * 1.01,
            low=p * 0.99,
            close=p,
            volume=1_000_000,
        )
        for i, p in enumerate(prices)
    ]


def test_no_lookahead_signal_executes_next_bar_open():
    """A buy signal generated on bar T should fill on bar T+1's open."""
    # Construct a price series where momentum triggers at bar idx=10
    prices = [100.0] * 10 + [101.0, 102.0, 103.0, 104.0, 105.0]
    bars = _bars_from_prices(prices)

    strat = MomentumStrategy({"sma_period": 5})
    cfg = BacktestConfig(
        ticker="TEST",
        strategy=strat,
        start_date=bars[0].date,
        end_date=bars[-1].date,
        initial_capital=10_000.0,
        slippage_bps=0.0,
        commission_pct=0.0,
        commission_per_share=0.0,
    )
    result = run_backtest(cfg, bars)

    buys = [t for t in result.trades if t.side == "buy"]
    assert buys, "expected at least one buy"
    first_buy = buys[0]
    buy_bar_idx = next(i for i, b in enumerate(bars) if b.date == first_buy.date)
    # Fill price must equal bar.open (next-bar open execution), NOT bar.close
    assert math.isclose(first_buy.price, bars[buy_bar_idx].open, rel_tol=1e-9), (
        f"Look-ahead bug: filled at {first_buy.price} but bar open is "
        f"{bars[buy_bar_idx].open} and close is {bars[buy_bar_idx].close}"
    )


def test_slippage_applied_to_buys():
    prices = [100.0] * 10 + [101.0, 102.0, 103.0, 104.0, 105.0]
    bars = _bars_from_prices(prices)
    strat = MomentumStrategy({"sma_period": 5})
    cfg = BacktestConfig(
        ticker="TEST",
        strategy=strat,
        start_date=bars[0].date,
        end_date=bars[-1].date,
        initial_capital=10_000.0,
        slippage_bps=10.0,  # 10 bps = 0.1%
        commission_pct=0.0,
        commission_per_share=0.0,
    )
    result = run_backtest(cfg, bars)

    buys = [t for t in result.trades if t.side == "buy"]
    assert buys
    first_buy = buys[0]
    buy_bar_idx = next(i for i, b in enumerate(bars) if b.date == first_buy.date)
    expected = bars[buy_bar_idx].open * 1.001
    assert math.isclose(first_buy.price, expected, rel_tol=1e-6)


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #
def test_walk_forward_smoke():
    # 200 bars of synthetic random walk
    rng = np.random.default_rng(0)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200))).tolist()
    bars = _bars_from_prices(prices)

    res = run_walk_forward(
        ticker="TEST",
        strategy_type="momentum",
        bars=bars,
        param_ranges={
            "sma_period": {"type": "int", "min": 5, "max": 20, "step": 5},
        },
        n_windows=3,
        initial_capital=10_000.0,
    )
    assert res.n_windows >= 1
    assert res.grid_size == 4  # 4 sma periods
    assert len(res.windows) == res.n_windows
    # Each window should have valid params and a numeric OOS Sharpe
    for w in res.windows:
        assert "sma_period" in w.best_params
        assert isinstance(w.oos_sharpe, float)
