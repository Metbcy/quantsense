"""Statistical significance testing for backtest results.

Two tests, both standard in quant research:

  1. **Bootstrap CI on Sharpe** — resample daily returns with replacement,
     compute Sharpe per resample, build a percentile confidence interval.
     Lets you say "Sharpe = 1.4, 95% CI [0.6, 2.1]" instead of pretending
     the point estimate is the truth.

  2. **Monte Carlo permutation test** — shuffle the daily returns and ask:
     how often does a random reshuffling produce a Sharpe at least as good?
     This p-value answers "is this strategy distinguishable from luck on
     the same return distribution?"

Both tests treat the daily strategy returns as the unit of analysis. They
do NOT account for parameter selection bias — that's what the deflated
Sharpe in `metrics.py` is for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .metrics import sharpe_ratio


@dataclass
class BootstrapCI:
    point_estimate: float
    ci_low: float
    ci_high: float
    confidence: float
    n_resamples: int


@dataclass
class PermutationTest:
    observed_sharpe: float
    p_value: float
    null_mean: float
    null_std: float
    n_permutations: int


def bootstrap_sharpe_ci(
    returns: np.ndarray,
    *,
    n_resamples: int = 2_000,
    confidence: float = 0.95,
    rng_seed: int | None = 42,
) -> BootstrapCI:
    """Stationary i.i.d. bootstrap CI on Sharpe.

    Note: assumes returns are roughly i.i.d. For autocorrelated series a
    block bootstrap would be more correct; we keep it simple here.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 5:
        raise ValueError("Need >= 5 return observations to bootstrap")

    rng = np.random.default_rng(rng_seed)
    n = len(returns)
    sharpes = np.empty(n_resamples, dtype=np.float64)
    for i in range(n_resamples):
        sample = returns[rng.integers(0, n, size=n)]
        sharpes[i] = sharpe_ratio(sample)

    alpha = 1.0 - confidence
    lo = float(np.percentile(sharpes, 100 * alpha / 2))
    hi = float(np.percentile(sharpes, 100 * (1 - alpha / 2)))

    return BootstrapCI(
        point_estimate=float(sharpe_ratio(returns)),
        ci_low=lo,
        ci_high=hi,
        confidence=confidence,
        n_resamples=n_resamples,
    )


def permutation_test_sharpe(
    returns: np.ndarray,
    *,
    n_permutations: int = 2_000,
    rng_seed: int | None = 42,
) -> PermutationTest:
    """Permutation test on Sharpe ratio.

    H0: the order of returns is irrelevant (any permutation is equally
    likely to produce this Sharpe). Under i.i.d. null this is true; if the
    observed Sharpe is in the right tail, we reject H0 and conclude the
    strategy's signal carries information beyond the return distribution.

    Returns a one-sided p-value (right tail).
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 5:
        raise ValueError("Need >= 5 return observations to permute")

    rng = np.random.default_rng(rng_seed)
    observed = sharpe_ratio(returns)

    null = np.empty(n_permutations, dtype=np.float64)
    for i in range(n_permutations):
        null[i] = sharpe_ratio(rng.permutation(returns))

    # +1 / +1 correction (Phipson-Smyth) to keep p-value > 0
    p = float((np.sum(null >= observed) + 1) / (n_permutations + 1))

    return PermutationTest(
        observed_sharpe=float(observed),
        p_value=p,
        null_mean=float(np.mean(null)),
        null_std=float(np.std(null)),
        n_permutations=n_permutations,
    )


def returns_from_equity(equity_curve: np.ndarray) -> np.ndarray:
    """Convenience: equity curve -> daily simple returns."""
    eq = np.asarray(equity_curve, dtype=np.float64)
    if len(eq) < 2:
        return np.array([], dtype=np.float64)
    return np.diff(eq) / eq[:-1]
