"""Reproducibility contract tests.

Same (price_data, BacktestConfig, code_version) MUST produce
byte-identical results across runs:

* equity curves
* trade lists
* bootstrap (i.i.d. and block) CIs
* permutation p-values
* walk-forward window selections
* `compute_run_hash` digest

These are regression guards against any future change that introduces
non-determinism (unseeded `np.random`, dict-iteration leaks, parallel
ordering, etc.).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from data.provider import OHLCVBar
from engine.backtest import BacktestConfig, run_backtest
from engine.run_hash import (
    CODE_VERSION,
    compute_run_hash,
    seed_from_run_hash,
)
from engine.significance import (
    bootstrap_sharpe_block,
    bootstrap_sharpe_ci,
    permutation_test_sharpe,
)
from engine.strategy import MomentumStrategy
from engine.walk_forward import run_walk_forward


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _make_bars(seed: int = 0, n: int = 200) -> list[OHLCVBar]:
    """Synthetic OHLCV bars from a seeded geometric random walk."""
    rng = np.random.default_rng(seed)
    prices = (100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))).tolist()
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


def _make_config(bars: list[OHLCVBar], sma_period: int = 10) -> BacktestConfig:
    return BacktestConfig(
        ticker="TEST",
        strategy=MomentumStrategy({"sma_period": sma_period}),
        start_date=bars[0].date,
        end_date=bars[-1].date,
        initial_capital=10_000.0,
        slippage_bps=0.0,
        commission_pct=0.0,
        commission_per_share=0.0,
    )


# --------------------------------------------------------------------------- #
# Engine determinism
# --------------------------------------------------------------------------- #
def test_same_config_same_equity_curve():
    """Same BacktestConfig + same bars -> byte-identical equity curve, trades, metrics."""
    bars = _make_bars()
    cfg1 = _make_config(bars)
    cfg2 = _make_config(bars)

    r1 = run_backtest(cfg1, bars)
    r2 = run_backtest(cfg2, bars)

    # Equity curves: list of (date, float) tuples; full byte-identity required.
    assert r1.equity_curve == r2.equity_curve, (
        "Equity curve diverged across two runs of the same config"
    )
    # Trades: deep equality on the list of dataclass records.
    assert r1.trades == r2.trades, "Trade list diverged across two runs"
    # Final equity scalar identity (catches any FP-order leak).
    assert r1.equity_curve[-1][1] == r2.equity_curve[-1][1]
    # Headline metrics.
    assert r1.metrics.sharpe_ratio == r2.metrics.sharpe_ratio
    assert r1.metrics.total_return_pct == r2.metrics.total_return_pct
    assert r1.metrics.max_drawdown_pct == r2.metrics.max_drawdown_pct


# --------------------------------------------------------------------------- #
# Significance determinism (the actual failure mode that motivated this todo)
# --------------------------------------------------------------------------- #
def test_same_config_same_bootstrap_ci():
    rng = np.random.default_rng(7)
    rets = rng.normal(0.001, 0.01, 252)

    a = bootstrap_sharpe_ci(rets, n_resamples=500, seed=42)
    b = bootstrap_sharpe_ci(rets, n_resamples=500, seed=42)

    assert a.ci_low == b.ci_low
    assert a.ci_high == b.ci_high
    assert a.point_estimate == b.point_estimate
    assert a.n_resamples == b.n_resamples


def test_same_config_same_block_ci():
    rng = np.random.default_rng(7)
    rets = rng.normal(0.001, 0.01, 252)

    a = bootstrap_sharpe_block(rets, n_resamples=300, seed=42)
    b = bootstrap_sharpe_block(rets, n_resamples=300, seed=42)

    assert a.ci_low == b.ci_low
    assert a.ci_high == b.ci_high
    assert a.point_estimate == b.point_estimate
    assert a.avg_block_length == b.avg_block_length


def test_same_config_same_permutation_pvalue():
    rng = np.random.default_rng(7)
    rets = rng.normal(0.001, 0.01, 252)

    a = permutation_test_sharpe(rets, n_permutations=300, seed=42)
    b = permutation_test_sharpe(rets, n_permutations=300, seed=42)

    assert a.p_value == b.p_value
    assert a.null_mean == b.null_mean
    assert a.null_std == b.null_std
    assert a.observed_sharpe == b.observed_sharpe


# --------------------------------------------------------------------------- #
# Walk-forward determinism — covers the dict-iteration-order risk
# --------------------------------------------------------------------------- #
def test_same_config_same_walk_forward():
    """Two walk-forward runs with the same seed pick the same params per window."""
    bars = _make_bars(seed=0, n=200)
    kwargs = dict(
        ticker="TEST",
        strategy_type="momentum",
        bars=bars,
        param_ranges={
            "sma_period": {"type": "int", "min": 5, "max": 20, "step": 5},
        },
        n_windows=3,
        initial_capital=10_000.0,
        seed=42,
    )

    a = run_walk_forward(**kwargs)
    b = run_walk_forward(**kwargs)

    assert a.n_windows == b.n_windows
    assert a.grid_size == b.grid_size
    assert len(a.windows) == len(b.windows)
    for w1, w2 in zip(a.windows, b.windows):
        assert w1.best_params == w2.best_params, (
            f"Walk-forward picked different params for window {w1.window_idx}: "
            f"{w1.best_params} vs {w2.best_params}"
        )
        assert w1.is_sharpe == w2.is_sharpe
        assert w1.oos_sharpe == w2.oos_sharpe
    assert a.aggregate_oos_sharpe == b.aggregate_oos_sharpe
    assert a.deflated_sharpe_ratio == b.deflated_sharpe_ratio


# --------------------------------------------------------------------------- #
# Run hash contract
# --------------------------------------------------------------------------- #
def test_run_hash_stable_under_no_change():
    bars = _make_bars()
    cfg = _make_config(bars)
    h1 = compute_run_hash(bars, cfg, code_version="test-v1")
    h2 = compute_run_hash(bars, cfg, code_version="test-v1")
    assert h1 == h2
    assert len(h1) == 16
    # And it must be hex.
    int(h1, 16)


def test_run_hash_changes_when_param_changes():
    bars = _make_bars()
    cfg_a = _make_config(bars, sma_period=10)
    cfg_b = _make_config(bars, sma_period=20)
    assert compute_run_hash(bars, cfg_a, code_version="v") != compute_run_hash(
        bars, cfg_b, code_version="v"
    )


def test_run_hash_changes_when_data_changes():
    bars = _make_bars()
    cfg = _make_config(bars)

    bars_perturbed = list(bars)
    b = bars_perturbed[5]
    bars_perturbed[5] = OHLCVBar(
        date=b.date,
        open=b.open,
        high=b.high,
        low=b.low,
        close=b.close + 1.0,  # flip one close price
        volume=b.volume,
    )
    assert compute_run_hash(bars, cfg, code_version="v") != compute_run_hash(
        bars_perturbed, cfg, code_version="v"
    )


def test_run_hash_changes_with_code_version():
    bars = _make_bars()
    cfg = _make_config(bars)
    assert compute_run_hash(bars, cfg, code_version="v1") != compute_run_hash(
        bars, cfg, code_version="v2"
    )


def test_seed_from_run_hash_is_deterministic_int():
    bars = _make_bars()
    cfg = _make_config(bars)
    h = compute_run_hash(bars, cfg, code_version="v")
    s1 = seed_from_run_hash(h)
    s2 = seed_from_run_hash(h)
    assert s1 == s2
    assert isinstance(s1, int)
    # First 8 hex chars -> 32-bit unsigned range.
    assert 0 <= s1 < 2**32


def test_code_version_captured_at_import():
    """Module-level CODE_VERSION should be a non-empty string ('dev' or a sha)."""
    assert isinstance(CODE_VERSION, str)
    assert CODE_VERSION  # non-empty
