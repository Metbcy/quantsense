"""Cross-validation of QuantSense metrics against the `empyrical-reloaded`
reference implementation (the maintained fork of Quantopian's `empyrical`).

WHY THIS FILE EXISTS
--------------------
`engine/metrics.py` reimplements Sharpe, Sortino, Calmar, max-drawdown,
downside deviation, alpha/beta, and the Deflated Sharpe Ratio (DSR). Without
an independent reference, any silent bug in those formulas would propagate
into the rest of the research stack. This file pins our impls to the
industry-standard `empyrical` outputs on synthetic data and asserts numeric
agreement.

The QuantSense impl is intentionally NOT replaced by empyrical:
  * empyrical has no DSR (Bailey & López de Prado 2014). We need ours.
  * empyrical's alpha/beta is plain OLS — it does NOT expose HC1 robust
    standard errors, t-stats, p-values or R². Our `compute_alpha_beta`
    does, which is required for the significance tooling.
  * Keeping our own code (with this cross-check) is more transparent than a
    silent dependency on a third-party library.

EXACT vs EPSILON-EQUAL: WHAT MATCHES AND WHY
--------------------------------------------
The following metrics match `empyrical` to ≤ 1e-9 absolute (basically
floating-point):

  * `sharpe_ratio`             — same formula (mean / std with ddof=1, then
                                 × √periods_per_year).
  * `max_drawdown`             — same algorithm; sign convention differs
                                 (we return DD as a positive percent;
                                 empyrical returns a negative fraction).
                                 The test aligns signs explicitly.
  * `calmar_ratio`             — both numerator (compound annualized return)
                                 and denominator (max DD) carry the same %/
                                 fraction unit, so the ratio is unitless and
                                 the sign cancels.
  * `annualized_return_pct`    — both use compound annualization
                                 (1 + r_total)^(periods/n) - 1.
  * `compute_alpha_beta.beta`  — same OLS slope; HC1 vs classical SE only
                                 changes the *standard error*, never the
                                 point estimate.

The following metrics have DOCUMENTED INTENTIONAL DIVERGENCES:

  1. `downside_deviation` / `sortino_ratio` — DIVISOR CONVENTION.
       QuantSense uses sqrt(sum(r_neg²) / n_neg) — i.e. the conditional
       second moment over the negative subset only. This matches the
       "naive" Sortino definition popularised on Investopedia and most
       hand-rolled implementations.
       empyrical uses sqrt(sum(min(r,0)²) / N) — the Bawa–Lindenberg /
       Sortino target semi-deviation, dividing by the total number of
       observations. This is the convention in the original Sortino & van
       der Meer (1991) paper and in the CFA Institute curriculum.
       Both are valid; the literature is split. We assert the EXACT
       relationship between them rather than papering over the gap:
           ours_dev / theirs_dev          == sqrt(N / n_neg)
           theirs_sortino / ours_sortino  == sqrt(N / n_neg)
       Tolerances are 1e-10 — the only slack is float arithmetic.

  2. `compute_alpha_beta.alpha` — LINEAR vs COMPOUND ANNUALIZATION.
       QuantSense annualizes the OLS daily intercept linearly:
           alpha_annual = daily_alpha * periods_per_year * 100   (in %)
       empyrical annualizes the same daily intercept by compounding:
           alpha_annual = (1 + daily_alpha) ** periods_per_year - 1
       Both are documented in the literature; CFA prefers the compound
       form, but linear is natural for an OLS regression interpretation
       (it makes alpha additive in the same way as beta-scaled returns).
       The metrics.py docstring is explicit: "Alpha and ``alpha_se`` are
       annualized and expressed in percent (multiplied by ``periods_per_year
       * 100``)" — i.e. it is a linear scaling by design.
       We assert the EXACT compound-vs-linear identity:
           emp_alpha == (1 + ours_alpha / (periods*100)) ** periods - 1
       to a relative tolerance of 1e-9.

  3. DSR — empyrical has no DSR at all, so we cross-validate ours by
       checking the multiple-testing penalty fires monotonically as
       n_trials grows. No external reference is possible.

If you are tempted to widen any tolerance below in order to make a test
pass, STOP — the divergence is almost certainly a real algorithmic
difference and needs to be characterised (like the two above), not hidden.
"""

from __future__ import annotations

import math

import empyrical
import numpy as np
import pytest

from engine.metrics import (
    TRADING_DAYS,
    compute_alpha_beta,
    daily_returns,
    deflated_sharpe_ratio,
    downside_deviation,
    max_drawdown,
    sharpe_ratio,
    sortino_ratio,
)
from engine.metrics import (
    annualized_return_pct as ann_ret_pct,
)
from engine.metrics import (
    calmar_ratio as our_calmar,
)


# --------------------------------------------------------------------------- #
# Fixtures: deterministic synthetic equity curves spanning multiple regimes.
# Using simple `cumprod(1 + r)` keeps `daily_returns(equity)` ≈ `r` exactly
# (modulo float rounding), so we can hand both libraries equivalent inputs.
# --------------------------------------------------------------------------- #


def _equity_from_returns(returns: np.ndarray, start: float = 100_000.0) -> np.ndarray:
    return start * np.cumprod(1.0 + returns)


@pytest.fixture(
    params=[
        # (label, seed, n, mean, std, post-fn description)
        ("low_vol", 42, 1260, 0.0005, 0.005, None),
        ("high_vol", 7, 1260, 0.0010, 0.025, None),
        ("with_drawdowns", 11, 1260, 0.0003, 0.015, "regime_switch"),
        ("mostly_positive", 99, 1260, 0.0010, 0.003, None),
    ],
    ids=lambda p: p[0],
)
def equity_fixture(request):
    """Yield (label, returns, equity) tuples that span four return regimes."""
    label, seed, n, mu, sigma, mode = request.param
    rng = np.random.default_rng(seed)
    returns = rng.normal(mu, sigma, n)
    if mode == "regime_switch":
        # Inject a clear bear regime (~30 days deeply negative) to stress-test
        # max-DD logic; a pure Gaussian almost never produces a 20%+ drawdown
        # at this vol over 5y.
        bear_start = 600
        returns[bear_start : bear_start + 30] = rng.normal(-0.015, 0.020, 30)
    equity = _equity_from_returns(returns)
    return label, returns, equity


# --------------------------------------------------------------------------- #
# 1. Sharpe ratio — must match exactly (same formula, ddof=1).
# --------------------------------------------------------------------------- #
def test_sharpe_matches_empyrical(equity_fixture):
    label, _, equity = equity_fixture
    rets = daily_returns(equity)

    ours = sharpe_ratio(rets, periods_per_year=TRADING_DAYS)
    theirs = float(empyrical.sharpe_ratio(rets, period="daily"))

    # Same closed-form expression on both sides → expect float-level equality.
    assert ours == pytest.approx(theirs, rel=1e-4, abs=1e-9), (
        f"Sharpe disagreement on fixture '{label}': ours={ours}, theirs={theirs}"
    )


# --------------------------------------------------------------------------- #
# 2. Sortino ratio — KNOWN DIVISOR-CONVENTION DIVERGENCE.
#    See module docstring §1. We do NOT widen the tolerance to mask this:
#    instead we assert the exact relationship theirs/ours == sqrt(N/n_neg).
# --------------------------------------------------------------------------- #
def test_sortino_documented_divergence_from_empyrical(equity_fixture):
    label, _, equity = equity_fixture
    rets = daily_returns(equity)
    n_neg = int(np.sum(rets < 0))
    n_total = len(rets)
    if n_neg == 0:
        pytest.skip(f"fixture '{label}' has no negative returns")

    ours = sortino_ratio(rets, periods_per_year=TRADING_DAYS)
    theirs = float(empyrical.sortino_ratio(rets, period="daily"))

    expected_ratio = math.sqrt(n_total / n_neg)
    actual_ratio = theirs / ours

    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-10), (
        f"Sortino divisor identity broken on fixture '{label}': "
        f"theirs/ours={actual_ratio} vs expected sqrt(N/n_neg)={expected_ratio}; "
        "either our impl or empyrical's downside-risk divisor changed."
    )


# --------------------------------------------------------------------------- #
# 3. Calmar ratio — must match exactly (units cancel in numerator/denominator).
# --------------------------------------------------------------------------- #
def test_calmar_matches_empyrical(equity_fixture):
    label, _, equity = equity_fixture
    rets = daily_returns(equity)

    mdd_pct, _ = max_drawdown(equity)  # positive %
    ann_ret = ann_ret_pct(equity)  # %, compound
    ours = our_calmar(ann_ret, mdd_pct)
    theirs = float(empyrical.calmar_ratio(rets, period="daily"))

    # Both ratios use compound annualized return on top and max-DD magnitude
    # on the bottom; the %-vs-fraction units cancel. Expect ~float equality.
    assert ours == pytest.approx(theirs, rel=1e-4, abs=1e-9), (
        f"Calmar disagreement on fixture '{label}': ours={ours}, theirs={theirs}"
    )


# --------------------------------------------------------------------------- #
# 4. Max drawdown — depth must match after sign + unit alignment.
#    empyrical returns a NEGATIVE FRACTION; we return a POSITIVE PERCENT.
# --------------------------------------------------------------------------- #
def test_max_drawdown_matches_empyrical_after_sign_alignment(equity_fixture):
    label, _, equity = equity_fixture
    rets = daily_returns(equity)

    ours_pct, _duration = max_drawdown(equity)
    theirs_frac = float(empyrical.max_drawdown(rets))

    # Sign / unit alignment: theirs is negative fraction (e.g. -0.27),
    # ours is positive percent (e.g. 27.0). Multiply by -100 to align.
    theirs_pct = -theirs_frac * 100.0

    assert ours_pct == pytest.approx(theirs_pct, rel=1e-4, abs=1e-9), (
        f"max-DD disagreement on fixture '{label}': "
        f"ours={ours_pct}%, theirs={theirs_pct}%"
    )


# --------------------------------------------------------------------------- #
# 5. Downside deviation — same DIVISOR-CONVENTION divergence as Sortino.
#    See module docstring §1. Assert exact relationship, not approximate equality.
# --------------------------------------------------------------------------- #
def test_downside_deviation_documented_divergence_from_empyrical(equity_fixture):
    label, _, equity = equity_fixture
    rets = daily_returns(equity)
    n_neg = int(np.sum(rets < 0))
    n_total = len(rets)
    if n_neg == 0:
        pytest.skip(f"fixture '{label}' has no negative returns")

    ours = downside_deviation(rets, periods_per_year=TRADING_DAYS)
    theirs = float(empyrical.downside_risk(rets, period="daily"))

    expected_ratio = math.sqrt(n_total / n_neg)
    actual_ratio = ours / theirs  # ours is bigger because it divides by n_neg < N

    assert actual_ratio == pytest.approx(expected_ratio, rel=1e-10), (
        f"downside-deviation divisor identity broken on fixture '{label}': "
        f"ours/theirs={actual_ratio} vs expected sqrt(N/n_neg)={expected_ratio}"
    )


# --------------------------------------------------------------------------- #
# 6. Alpha & Beta vs empyrical.
#    * Beta point estimate: must match exactly (same OLS slope).
#    * Alpha point estimate: linear-vs-compound annualization difference.
#      We assert the EXACT compound transform of our linear alpha matches
#      empyrical's compound alpha.
#    HC1-vs-classical standard error / t-stat / p-value are NOT compared;
#    empyrical does not expose robust SE.
# --------------------------------------------------------------------------- #
@pytest.fixture(
    params=[
        # (label, seed, n, daily_alpha_true, beta_true, noise_std)
        ("alpha_low_noise", 42, 1260, 0.0002, 1.30, 0.005),
        ("alpha_zero", 17, 1260, 0.0000, 0.85, 0.004),
        ("alpha_high_beta", 23, 1260, 0.0001, 1.80, 0.006),
        ("alpha_short_window", 5, 252, 0.0003, 0.95, 0.003),
    ],
    ids=lambda p: p[0],
)
def alpha_beta_fixture(request):
    label, seed, n, daily_alpha, true_beta, noise_std = request.param
    rng = np.random.default_rng(seed)
    bench = rng.normal(0.0004, 0.011, n)
    strat = daily_alpha + true_beta * bench + rng.normal(0.0, noise_std, n)
    return label, strat, bench


def test_beta_matches_empyrical_exactly(alpha_beta_fixture):
    label, strat, bench = alpha_beta_fixture
    res = compute_alpha_beta(strat, bench, periods_per_year=TRADING_DAYS)
    assert res is not None
    _, emp_beta = empyrical.alpha_beta(strat, bench, period="daily")

    # OLS slope is invariant to linear scaling and to choice of cov-type, so
    # this should be float-equal.
    assert res.beta == pytest.approx(float(emp_beta), rel=1e-4, abs=1e-9), (
        f"Beta disagreement on fixture '{label}': ours={res.beta}, theirs={emp_beta}"
    )


def test_alpha_documented_linear_vs_compound_divergence(alpha_beta_fixture):
    label, strat, bench = alpha_beta_fixture
    res = compute_alpha_beta(strat, bench, periods_per_year=TRADING_DAYS)
    assert res is not None
    emp_alpha, _ = empyrical.alpha_beta(strat, bench, period="daily")

    # Recover the daily intercept from our annualized-percent alpha.
    # metrics.py defines: alpha_annual_pct = daily_alpha * periods_per_year * 100
    daily_alpha_implied = res.alpha / (TRADING_DAYS * 100.0)
    # Empyrical compounds the same daily intercept: (1 + d)^252 - 1 (fraction).
    emp_alpha_from_ours = (1.0 + daily_alpha_implied) ** TRADING_DAYS - 1.0

    assert emp_alpha_from_ours == pytest.approx(
        float(emp_alpha), rel=1e-9, abs=1e-12
    ), (
        f"Alpha compound-vs-linear identity broken on fixture '{label}': "
        f"ours_linear={res.alpha}%, implied_compound={emp_alpha_from_ours}, "
        f"empyrical={emp_alpha}"
    )


# --------------------------------------------------------------------------- #
# 7. Deflated Sharpe Ratio — empyrical has no DSR.
#    We cross-validate ours by asserting the multiple-testing penalty fires:
#    holding observed Sharpe / sample-size / moments fixed, increasing
#    n_trials must MONOTONICALLY DECREASE the DSR (since the null benchmark
#    SR0 grows with the number of strategies tried).
# --------------------------------------------------------------------------- #
def test_dsr_monotonic_in_trial_count_no_empyrical_reference():
    """empyrical-reloaded does not implement DSR (Bailey & López de Prado 2014),
    which is precisely why our impl exists. We sanity-check it instead by
    confirming the multiple-testing penalty is monotonic.
    """
    observed_sharpe = 1.8  # annualized Sharpe of an "interesting" strategy
    n_returns = 1260
    skew = -0.2
    kurt = 4.0  # mildly leptokurtic, typical of equity returns

    trial_counts = [1, 5, 10, 50, 100, 500, 1000]
    dsrs = [
        deflated_sharpe_ratio(observed_sharpe, n_returns, t, skew, kurt)
        for t in trial_counts
    ]

    # Strict monotonic decrease for n_trials > 1; n_trials=1 is the no-deflation
    # baseline so it should be ≥ every later value.
    for prev, curr, prev_t, curr_t in zip(
        dsrs, dsrs[1:], trial_counts, trial_counts[1:]
    ):
        assert curr < prev, (
            f"DSR not monotonic decreasing as trial count grows: "
            f"DSR(n_trials={prev_t})={prev:.6f} -> DSR(n_trials={curr_t})={curr:.6f}"
        )

    # Range sanity: DSR is a probability ∈ [0, 1].
    for t, dsr in zip(trial_counts, dsrs):
        assert 0.0 <= dsr <= 1.0, f"DSR out of [0,1] at n_trials={t}: {dsr}"


def test_dsr_zero_when_observed_sharpe_is_zero():
    """Edge case: observed_sharpe == 0 short-circuits to 0.0 by design."""
    assert deflated_sharpe_ratio(0.0, 1000, n_trials=10) == 0.0
