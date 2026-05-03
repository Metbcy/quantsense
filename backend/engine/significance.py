"""Statistical significance testing for backtest results.

Four tests, all standard in quant research:

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

  4. **Hansen (2005) Superior Predictive Ability (SPA) test** — given N
     candidate strategies and a benchmark, what is the probability that
     the *best* strategy is genuinely better than the benchmark vs.
     data-mined? Uses a stationary block bootstrap on the loss
     differentials (return_k - return_benchmark) to build the null
     distribution of the studentized max statistic. Returns both the
     conservative all-recentered p-value and Hansen's recommended
     consistent (threshold-recentered) p-value.

Bootstrap CI variants are surfaced side-by-side so the user can see the
spread between them — that spread is exactly the autocorrelation
correction. None of the single-strategy tests account for parameter
selection bias across a sweep — that's what the deflated Sharpe in
`metrics.py` is for. The SPA test handles selection bias across an
explicit *set* of competing strategies.
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


@dataclass
class SPAResult:
    best_strategy_index: int
    best_sharpe: float
    spa_pvalue: float  # H0: best strategy is no better than benchmark (conservative / all-recentered)
    spa_pvalue_consistent: float  # Hansen's recommended threshold-recentered version
    n_strategies: int
    n_resamples: int
    n_obs: int
    block_length: float


def _spa_hac_variance(d: np.ndarray, block_length: float) -> np.ndarray:
    """HAC-style variance of the loss-differential mean.

    Matches the asymptotic (non-nested) variance estimator used in
    Hansen (2005) and in `arch.bootstrap.SPA._compute_variance`. The
    kernel weights kappa_i derive from the geometric block-length
    distribution of the stationary bootstrap with parameter
    p = 1/block_length.
    """
    t = d.shape[0]
    demeaned = d - d.mean(axis=0)
    p = 1.0 / float(block_length)
    variances = np.sum(demeaned**2, axis=0) / t
    for i in range(1, t):
        kappa = ((1.0 - i / t) * ((1.0 - p) ** i)) + ((i / t) * ((1.0 - p) ** (t - i)))
        variances += 2.0 * kappa * np.sum(demeaned[: t - i] * demeaned[i:], axis=0) / t
    # Numerical guard: variances must be strictly positive for studentization.
    return np.maximum(variances, np.finfo(np.float64).tiny)


def hansens_spa_test(
    strategy_returns_list: list[np.ndarray],
    benchmark_returns: np.ndarray,
    *,
    n_resamples: int = 5000,
    block_length: float | None = None,
    seed: int | None = None,
) -> SPAResult:
    """Hansen (2005) Superior Predictive Ability test.

    Given N candidate strategies and a benchmark, computes the
    probability that the *best* strategy's outperformance is genuine
    rather than the result of data mining across the N candidates.

    **When to use this vs. the Deflated Sharpe Ratio**: DSR (Bailey &
    López de Prado 2014, in `metrics.py`) corrects for selection bias
    when you've swept many *parameter combinations* of one strategy
    family. SPA is the right tool when you have an explicit *set* of
    competing strategies (possibly different families) and want a
    principled, autocorrelation-aware p-value on the best-vs-benchmark
    comparison. Both control different forms of multiple testing; they
    are complementary, not redundant.

    The loss differential is `d_k(t) = L_benchmark(t) - L_k(t)`. Loss is
    `-return`, so `d_k(t) = strategy_return_k(t) - benchmark_return(t)`
    (positive when strategy beats benchmark). The studentized test
    statistic is

        T_SPA = max(0, max_k sqrt(N) * mean(d_k) / sigma_k)

    where sigma_k is an HAC variance estimator consistent with the
    stationary block bootstrap kernel (see `_spa_hac_variance`).

    The bootstrap null distribution is built by resampling the loss
    differentials with `arch.bootstrap.StationaryBootstrap`. Two
    centering schemes are reported:

      * **`spa_pvalue`** — *naive / all-recentered*. Every strategy's
        bootstrap mean is shifted back to zero. This is the most
        conservative variant (largest p-value): even bad strategies
        contribute their full bootstrap noise to the null.
      * **`spa_pvalue_consistent`** — *Hansen's recommended consistent
        version*. Strategies whose empirical mean differential is below
        the threshold ``-sqrt((sigma_k^2 / N) * 2 log log N)`` are NOT
        recentered (they stay at their bad empirical mean in the
        bootstrap world, so they cannot drive the max). This produces a
        less conservative, asymptotically correct p-value and is the
        version Hansen recommends as the headline result.

    Parameters
    ----------
    strategy_returns_list : list[np.ndarray]
        One 1-D array of (daily) returns per candidate strategy. All
        arrays and `benchmark_returns` must have the same length.
    benchmark_returns : np.ndarray
        Benchmark return series (e.g. buy-and-hold of the underlying).
    n_resamples : int
        Bootstrap replicates. Default 5000.
    block_length : float | None
        Expected block length for the stationary bootstrap. If `None`,
        the Politis-White (2009) optimum is computed from the loss
        differentials (max across strategies, conservative choice).
    seed : int | None
        RNG seed forwarded to `StationaryBootstrap`. With a fixed seed,
        same inputs yield byte-identical p-values; `None` falls back to
        non-deterministic sampling.

    Edge cases
    ----------
    * `len(strategy_returns_list) == 0` → ValueError.
    * `len(strategy_returns_list) == 1` → runs cleanly. The test
      degenerates to a one-sample bootstrap test of whether the single
      strategy's mean differential vs the benchmark is positive (no
      multiple-testing correction needed; both reported p-values
      coincide for the consistent scheme since there is only one
      candidate to threshold).
    """
    if len(strategy_returns_list) == 0:
        raise ValueError("Need at least 1 strategy for the SPA test")

    benchmark = np.asarray(benchmark_returns, dtype=np.float64)
    n = benchmark.shape[0]
    if n < 5:
        raise ValueError("Need >= 5 return observations to run SPA")

    cols = []
    for i, s in enumerate(strategy_returns_list):
        arr = np.asarray(s, dtype=np.float64)
        if arr.shape != benchmark.shape:
            raise ValueError(
                f"Strategy {i} returns length {arr.shape} does not match "
                f"benchmark length {benchmark.shape}"
            )
        cols.append(arr)
    models = np.column_stack(cols)  # (T, K)
    k = models.shape[1]

    # Loss differentials d_k(t) = L_b - L_k = (-r_b) - (-r_k) = r_k - r_b
    d = models - benchmark[:, None]  # (T, K)

    # Block length: Politis-White optimal from the loss differentials,
    # taking the max across strategies to be conservative w.r.t. the
    # most-autocorrelated column.
    if block_length is None:
        opt = optimal_block_length(d)
        bl = float(np.max(np.asarray(opt["stationary"].values)))
    else:
        bl = float(block_length)
    bl = max(1.0, bl)

    # HAC variance & studentized observed stat
    variances = _spa_hac_variance(d, bl)
    std_d = np.sqrt(variances)
    mean_d = d.mean(axis=0)
    sqrt_n = np.sqrt(n)
    t_k = sqrt_n * mean_d / std_d
    t_spa = float(max(0.0, np.max(t_k)))

    # Centering schemes (g_k applied to bootstrap means before studentization)
    threshold = -np.sqrt((variances / n) * 2.0 * np.log(np.log(n)))
    g_naive = mean_d.copy()
    g_consistent = mean_d.copy()
    g_consistent[mean_d < threshold] = 0.0

    # Bootstrap distribution under H0
    bs = StationaryBootstrap(bl, d, seed=seed)
    t_b_naive = np.empty(n_resamples, dtype=np.float64)
    t_b_consistent = np.empty(n_resamples, dtype=np.float64)
    for i, (pos_arg, _) in enumerate(bs.bootstrap(n_resamples)):
        d_star_mean = pos_arg[0].mean(axis=0)
        z_naive = sqrt_n * (d_star_mean - g_naive) / std_d
        z_cons = sqrt_n * (d_star_mean - g_consistent) / std_d
        t_b_naive[i] = max(0.0, np.max(z_naive))
        t_b_consistent[i] = max(0.0, np.max(z_cons))

    p_naive = float(np.mean(t_b_naive >= t_spa))
    p_consistent = float(np.mean(t_b_consistent >= t_spa))

    best_idx = int(np.argmax(mean_d))
    best_sharpe = float(sharpe_ratio(models[:, best_idx]))

    return SPAResult(
        best_strategy_index=best_idx,
        best_sharpe=best_sharpe,
        spa_pvalue=p_naive,
        spa_pvalue_consistent=p_consistent,
        n_strategies=k,
        n_resamples=n_resamples,
        n_obs=n,
        block_length=bl,
    )
