"""Unit tests for the statsmodels-based alpha/beta regression in metrics.py."""

from __future__ import annotations

import numpy as np
import pytest
import statsmodels.api as sm

from engine.metrics import (
    TRADING_DAYS,
    AlphaBetaResult,
    alpha_beta,
    compute_all,
    compute_alpha_beta,
)


# --------------------------------------------------------------------------- #
# Known-output linear data: y = a + b*x + noise
# --------------------------------------------------------------------------- #
def test_compute_alpha_beta_recovers_known_slope_and_intercept():
    """y = 0.0005 + 1.5 * x + tiny noise → beta ≈ 1.5, alpha ≈ annualized 0.0005."""
    rng = np.random.default_rng(0)
    n = 500
    daily_alpha = 0.0005  # ~12.6% per year
    true_beta = 1.5
    x = rng.normal(0.0, 0.01, n)
    noise = rng.normal(0.0, 1e-4, n)
    y = daily_alpha + true_beta * x + noise

    res = compute_alpha_beta(y, x)
    assert isinstance(res, AlphaBetaResult)
    # Beta should land essentially on top of the true 1.5
    assert res.beta == pytest.approx(true_beta, abs=0.01)
    # Alpha is annualized in %: daily_alpha * 252 * 100
    expected_alpha_pct = daily_alpha * TRADING_DAYS * 100.0
    assert res.alpha == pytest.approx(expected_alpha_pct, rel=0.05)
    # With near-zero noise the fit should be near-perfect
    assert res.r_squared > 0.99
    # Beta is highly significant
    assert abs(res.beta_t) > 50
    assert res.beta_pvalue < 1e-10
    assert res.n_obs == n


def test_compute_alpha_beta_dict_serialization_has_required_keys():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.01, 100)
    y = 0.0001 + 0.8 * x + rng.normal(0, 0.001, 100)
    res = compute_alpha_beta(y, x)
    assert res is not None
    payload = res.to_dict()
    expected_keys = {
        "alpha",
        "alpha_se",
        "alpha_t",
        "alpha_pvalue",
        "beta",
        "beta_se",
        "beta_t",
        "beta_pvalue",
        "r_squared",
        "n_obs",
    }
    assert expected_keys.issubset(payload.keys())


# --------------------------------------------------------------------------- #
# Graceful degradation: missing / empty benchmark
# --------------------------------------------------------------------------- #
def test_compute_alpha_beta_none_benchmark_returns_none():
    s = np.array([0.01, -0.005, 0.002, 0.0, 0.003])
    assert compute_alpha_beta(s, None) is None
    assert compute_alpha_beta(None, s) is None
    assert compute_alpha_beta(None, None) is None


def test_compute_alpha_beta_empty_benchmark_returns_none():
    s = np.array([0.01, -0.005, 0.002, 0.0, 0.003])
    assert compute_alpha_beta(s, np.array([])) is None
    assert compute_alpha_beta(np.array([]), s) is None


def test_compute_alpha_beta_zero_variance_benchmark_returns_none():
    s = np.array([0.01, -0.005, 0.002, 0.0, 0.003])
    flat = np.zeros(5)
    assert compute_alpha_beta(s, flat) is None


def test_compute_all_no_benchmark_leaves_alpha_beta_fields_none():
    eq = 100_000 + np.cumsum(np.random.default_rng(2).normal(50, 200, 100))
    m = compute_all(eq)
    assert m.alpha is None
    assert m.beta is None
    assert m.alpha_se is None
    assert m.alpha_t is None
    assert m.alpha_pvalue is None
    assert m.beta_se is None
    assert m.beta_t is None
    assert m.beta_pvalue is None
    assert m.r_squared is None
    assert m.alpha_beta_n_obs is None


# --------------------------------------------------------------------------- #
# Length-mismatch must raise a clear ValueError
# --------------------------------------------------------------------------- #
def test_compute_alpha_beta_length_mismatch_raises_value_error():
    s = np.array([0.01, -0.005, 0.002, 0.0, 0.003])
    b = np.array([0.005, -0.002, 0.001])
    with pytest.raises(ValueError, match="same length"):
        compute_alpha_beta(s, b)


# --------------------------------------------------------------------------- #
# Low n_obs is allowed (caller can flag)
# --------------------------------------------------------------------------- #
def test_compute_alpha_beta_small_sample_still_returns_result():
    rng = np.random.default_rng(3)
    n = 10  # well below 30
    x = rng.normal(0, 0.01, n)
    y = 0.0002 + 1.1 * x + rng.normal(0, 0.001, n)
    res = compute_alpha_beta(y, x)
    assert res is not None
    assert res.n_obs == n
    assert res.n_obs < 30  # caller can flag this


# --------------------------------------------------------------------------- #
# HC1 robust SE differs from non-robust OLS SE under heteroskedasticity
# --------------------------------------------------------------------------- #
def test_hc1_se_differs_from_classical_ols_under_heteroskedasticity():
    """Construct heteroskedastic noise (sigma scales with |x|).

    HC1 robust SEs should diverge from the homoskedastic-assumption
    classical OLS SEs — that's the whole point of using HC1.
    """
    rng = np.random.default_rng(4)
    n = 400
    x = rng.normal(0, 0.01, n)
    # Variance of noise grows sharply with |x| → strong heteroskedasticity
    noise = rng.normal(0, 1.0, n) * (0.0002 + 5.0 * np.abs(x))
    y = 0.0001 + 0.9 * x + noise

    # Our implementation (HC1)
    hc1 = compute_alpha_beta(y, x)
    assert hc1 is not None

    # Reference: classical homoskedastic OLS SEs
    X = sm.add_constant(x, has_constant="add")
    classical = sm.OLS(y, X).fit()  # default cov_type='nonrobust'
    classical_beta_se = float(classical.bse[1])

    # Beta point-estimate must agree (same OLS fit, only cov differs)
    assert hc1.beta == pytest.approx(float(classical.params[1]), rel=1e-9)
    # But the HC1 standard error of beta must visibly disagree with the
    # homoskedastic SE — under this much heteroskedasticity it's typically
    # 30%+ different. We require >= 10% relative gap to keep the assertion
    # robust to RNG draws.
    rel_gap = abs(hc1.beta_se - classical_beta_se) / classical_beta_se
    assert rel_gap > 0.10, (
        f"HC1 beta_se={hc1.beta_se} too close to classical={classical_beta_se} "
        f"(rel gap={rel_gap:.3f}); HC1 should differ under heteroskedasticity"
    )


# --------------------------------------------------------------------------- #
# Back-compat shim: alpha_beta tuple wrapper still works
# --------------------------------------------------------------------------- #
def test_legacy_alpha_beta_tuple_wrapper_still_returns_two_floats():
    rng = np.random.default_rng(5)
    x = rng.normal(0, 0.01, 100)
    y = 0.0003 + 1.2 * x + rng.normal(0, 0.0005, 100)
    a, b = alpha_beta(y, x)
    assert isinstance(a, float)
    assert isinstance(b, float)
    assert b == pytest.approx(1.2, abs=0.05)


def test_legacy_alpha_beta_returns_zero_zero_on_bad_input():
    # Empty / single-point inputs should not raise — return (0.0, 0.0)
    assert alpha_beta(np.array([]), np.array([])) == (0.0, 0.0)
    assert alpha_beta(np.array([0.01]), np.array([0.005])) == (0.0, 0.0)
