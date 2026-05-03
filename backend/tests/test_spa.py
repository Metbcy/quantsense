"""Tests for Hansen 2005 Superior Predictive Ability test."""

from __future__ import annotations

import numpy as np
import pytest

from engine.significance import SPAResult, hansens_spa_test


def test_spa_identical_strategies_high_pvalue():
    """3 copies of the same return series → no real outperformance.

    The strategy itself has no edge over the benchmark (both drawn from
    the same distribution), so all three SPA p-values should be high.
    """
    rng = np.random.default_rng(0)
    benchmark = rng.normal(0.0, 0.01, 500)
    strat = rng.normal(0.0, 0.01, 500)

    res = hansens_spa_test(
        [strat, strat.copy(), strat.copy()],
        benchmark,
        n_resamples=1000,
        seed=42,
    )
    assert isinstance(res, SPAResult)
    assert res.n_strategies == 3
    assert res.spa_pvalue > 0.10, f"expected p>0.10 for noise, got {res.spa_pvalue}"
    assert res.spa_pvalue_consistent > 0.10


def test_spa_one_clear_winner_low_pvalue():
    """4 noise + 1 winner with clear positive drift → SPA detects winner."""
    rng = np.random.default_rng(42)
    n = 1000
    benchmark = rng.normal(0.0, 0.01, n)
    # 4 strategies with no edge over benchmark
    noise = [benchmark + rng.normal(0.0, 0.01, n) for _ in range(4)]
    # 1 strategy with a strong, persistent edge: +0.1% daily on top of benchmark
    winner = benchmark + rng.normal(0.001, 0.01, n)

    res = hansens_spa_test(noise + [winner], benchmark, n_resamples=2000, seed=42)
    assert res.best_strategy_index == 4, (
        f"expected winner at index 4, got {res.best_strategy_index}"
    )
    assert res.spa_pvalue < 0.05, (
        f"expected p<0.05 for clear winner, got {res.spa_pvalue}"
    )
    assert res.spa_pvalue_consistent <= res.spa_pvalue + 1e-12


def test_spa_deterministic_with_seed():
    """Same inputs + same seed → byte-identical p-values."""
    rng = np.random.default_rng(7)
    benchmark = rng.normal(0.0, 0.01, 500)
    strats = [rng.normal(0.0001, 0.01, 500) for _ in range(3)]

    a = hansens_spa_test(strats, benchmark, n_resamples=500, seed=123)
    b = hansens_spa_test(strats, benchmark, n_resamples=500, seed=123)
    assert a.spa_pvalue == b.spa_pvalue
    assert a.spa_pvalue_consistent == b.spa_pvalue_consistent
    assert a.block_length == b.block_length
    assert a.best_sharpe == b.best_sharpe

    # Different seed produces a different bootstrap draw → at least one
    # of the two p-values should differ.
    c = hansens_spa_test(strats, benchmark, n_resamples=500, seed=999)
    assert (a.spa_pvalue, a.spa_pvalue_consistent) != (
        c.spa_pvalue,
        c.spa_pvalue_consistent,
    )


def test_spa_block_length_passthrough():
    """Explicit block_length is reported verbatim; None → Politis-White > 1."""
    rng = np.random.default_rng(1)
    benchmark = rng.normal(0.0, 0.01, 400)
    strats = [rng.normal(0.0, 0.01, 400) for _ in range(3)]

    res_explicit = hansens_spa_test(
        strats, benchmark, n_resamples=200, block_length=10, seed=1
    )
    assert res_explicit.block_length == 10.0

    res_pw = hansens_spa_test(
        strats, benchmark, n_resamples=200, block_length=None, seed=1
    )
    assert res_pw.block_length > 1.0


def test_spa_single_strategy_runs_cleanly():
    """1 strategy degenerates to a one-sample bootstrap test."""
    rng = np.random.default_rng(3)
    benchmark = rng.normal(0.0, 0.01, 300)
    strat = benchmark + rng.normal(0.0, 0.01, 300)

    res = hansens_spa_test([strat], benchmark, n_resamples=500, seed=7)
    assert res.n_strategies == 1
    assert res.best_strategy_index == 0
    assert 0.0 <= res.spa_pvalue <= 1.0
    assert 0.0 <= res.spa_pvalue_consistent <= 1.0


def test_spa_zero_strategies_raises():
    with pytest.raises(ValueError):
        hansens_spa_test([], np.zeros(100))
