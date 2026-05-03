"""Statistical significance testing for backtest results.

Three tests, all standard in quant research:

  1. **i.i.d. bootstrap CI on Sharpe** — resample daily returns with
     replacement, compute Sharpe per resample, build a percentile
     confidence interval. Treats each daily return as independent.

  2. **Stationary block bootstrap CI on Sharpe** (Politis & Romano 1994) —
     resamples *blocks* of consecutive returns with geometrically
     distributed block lengths, preserving the short-run autocorrelation
     structure (volatility clustering, momentum, mean-reversion). Block
     length is chosen via the Politis-White (2009) data-driven optimum.
     For autocorrelated series this produces a more honest, typically
     wider CI than the i.i.d. version.

  3. **Monte Carlo permutation test** — sign-flip the daily returns and
     ask how often a random sign assignment produces a Sharpe at least as
     good. This p-value answers "is this strategy distinguishable from
     symmetric noise on the same return distribution?"

Both bootstrap variants are surfaced side-by-side so the user can see the
spread between them — that spread is exactly the autocorrelation
correction. None of these tests account for parameter selection bias —
that's what the deflated Sharpe in `metrics.py` is for.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from arch.bootstrap import StationaryBootstrap, optimal_block_length

from .metrics import sharpe_ratio


@dataclass
class BootstrapCI:
    point_estimate: float
    ci_low: float
    ci_high: float
    confidence: float
    n_resamples: int


@dataclass
class BlockBootstrapCI:
    point_estimate: float
    ci_low: float
    ci_high: float
    confidence: float
    n_resamples: int
    avg_block_length: float  # Politis-White optimal expected block length


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
    seed: int | None = 42,
) -> BootstrapCI:
    """i.i.d. bootstrap CI on Sharpe.

    Treats each daily return as exchangeable. Under-states uncertainty for
    autocorrelated series (volatility clustering, momentum). Use
    `bootstrap_sharpe_block` for an autocorrelation-aware alternative.

    `seed` controls reproducibility. The default (42) makes the function
    deterministic given the same returns; pass an explicit `None` to fall
    back to a non-deterministic `np.random.default_rng()`. We use the
    modern Generator API rather than the global `np.random` namespace so
    we never mutate process-wide state — important in a multi-request
    server.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 5:
        raise ValueError("Need >= 5 return observations to bootstrap")

    rng = np.random.default_rng(seed)
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


def bootstrap_sharpe_block(
    returns: np.ndarray,
    *,
    n_resamples: int = 2_000,
    confidence: float = 0.95,
    block_length: float | None = None,
    seed: int | None = 42,
) -> BlockBootstrapCI:
    """Stationary block bootstrap CI on Sharpe (Politis & Romano 1994).

    Resamples blocks of consecutive returns with geometrically
    distributed block lengths, preserving short-run autocorrelation
    structure that is destroyed by i.i.d. resampling. For typical daily
    equity-strategy returns this yields a wider, more honest CI than
    `bootstrap_sharpe_ci`.

    `block_length` is the *expected* (mean) block length. If None, it is
    estimated from the data via the Politis-White (2009) optimum
    (`arch.bootstrap.optimal_block_length`, "stationary" column). The
    estimator can return a value below 1 for very-low-autocorrelation
    series; we floor it at 1.0 (which makes the bootstrap degenerate to
    i.i.d. resampling, the right limit when no autocorrelation is
    detected).

    `seed` is forwarded to `arch.bootstrap.StationaryBootstrap`'s own
    seed kwarg. Default 42 makes the CI deterministic given the same
    returns; explicit `None` falls back to non-deterministic sampling.
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 5:
        raise ValueError("Need >= 5 return observations to bootstrap")

    if block_length is None:
        opt = optimal_block_length(returns)
        block_length = float(opt["stationary"].iloc[0])
    block_length = max(1.0, float(block_length))

    bs = StationaryBootstrap(block_length, returns, seed=seed)
    sharpes = bs.apply(sharpe_ratio, n_resamples).ravel()

    alpha = 1.0 - confidence
    lo = float(np.percentile(sharpes, 100 * alpha / 2))
    hi = float(np.percentile(sharpes, 100 * (1 - alpha / 2)))

    return BlockBootstrapCI(
        point_estimate=float(sharpe_ratio(returns)),
        ci_low=lo,
        ci_high=hi,
        confidence=confidence,
        n_resamples=n_resamples,
        avg_block_length=block_length,
    )


def permutation_test_sharpe(
    returns: np.ndarray,
    *,
    n_permutations: int = 2_000,
    seed: int | None = 42,
) -> PermutationTest:
    """Sign-flip permutation test on Sharpe ratio.

    H0: returns are noise around zero (symmetric, no edge). Under H0,
    flipping the sign of each return at random is exchangeable. We
    compute Sharpe on many sign-flipped copies to build a null
    distribution and report the right-tail p-value.

    Note: a plain order-permutation of a 1D returns vector leaves both
    mean and std unchanged, so it cannot test Sharpe at all. Sign-flip
    is the standard fix when you only have a single return series.

    `seed` is the RNG seed for the sign-flip draws. Default 42 yields a
    reproducible p-value; pass explicit `None` for non-deterministic
    behavior.

    Returns a one-sided p-value (right tail).
    """
    returns = np.asarray(returns, dtype=np.float64)
    if len(returns) < 5:
        raise ValueError("Need >= 5 return observations to permute")

    rng = np.random.default_rng(seed)
    observed = sharpe_ratio(returns)

    null = np.empty(n_permutations, dtype=np.float64)
    n = len(returns)
    for i in range(n_permutations):
        signs = rng.choice([-1.0, 1.0], size=n)
        null[i] = sharpe_ratio(returns * signs)

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
