"""Quant-grade performance metrics.

Goes beyond textbook Sharpe to provide the metrics that matter in practice:
  * Sortino ratio (downside-only volatility)
  * Calmar ratio (return / max DD)
  * Max drawdown depth AND duration (in bars)
  * Annualized return + downside deviation
  * Alpha & beta vs a benchmark series, with HC1 robust standard errors,
    t-stats, p-values and R² (via statsmodels OLS)
  * Deflated Sharpe Ratio (Bailey & López de Prado, 2014) — adjusts the
    observed Sharpe for selection bias when many strategies have been tried.

All functions are pure: take numpy arrays / lists of floats and return floats.
No dependence on `BacktestResult` so they are reusable from walk-forward
analysis, optimization, and significance testing.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import statsmodels.api as sm
from scipy import stats

TRADING_DAYS = 252


@dataclass
class AlphaBetaResult:
    """OLS regression of strategy returns on benchmark returns.

    Alpha and its standard error are annualized and expressed in percent
    (consistent with `annualized_return_pct`); the t-stat and p-value are
    invariant to that scaling. Beta and its diagnostics are unitless.
    Standard errors come from a heteroskedasticity-robust HC1 covariance
    matrix (statsmodels `cov_type='HC1'`).
    """

    alpha: float
    alpha_se: float
    alpha_t: float
    alpha_pvalue: float
    beta: float
    beta_se: float
    beta_t: float
    beta_pvalue: float
    r_squared: float
    n_obs: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PerformanceMetrics:
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_bars: int
    downside_deviation: float
    alpha: float | None  # annualized %; None if no benchmark provided
    beta: float | None
    deflated_sharpe_ratio: float
    # Richer regression diagnostics (HC1 robust); all None when no benchmark.
    alpha_se: float | None = None
    alpha_t: float | None = None
    alpha_pvalue: float | None = None
    beta_se: float | None = None
    beta_t: float | None = None
    beta_pvalue: float | None = None
    r_squared: float | None = None
    alpha_beta_n_obs: int | None = None


def daily_returns(equity: np.ndarray) -> np.ndarray:
    """Simple daily returns from an equity curve. Length = len(equity) - 1."""
    if len(equity) < 2:
        return np.array([], dtype=np.float64)
    return np.diff(equity) / equity[:-1]


def sharpe_ratio(returns: np.ndarray, periods_per_year: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std == 0.0:
        return 0.0
    return float(np.mean(returns)) / std * math.sqrt(periods_per_year)


def sortino_ratio(returns: np.ndarray, periods_per_year: int = TRADING_DAYS) -> float:
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0:
        return 0.0
    downside_std = float(np.sqrt(np.mean(downside**2)))
    if downside_std == 0.0:
        return 0.0
    return float(np.mean(returns)) / downside_std * math.sqrt(periods_per_year)


def calmar_ratio(annualized_return_pct: float, max_drawdown_pct: float) -> float:
    if max_drawdown_pct <= 0:
        return 0.0
    return annualized_return_pct / max_drawdown_pct


def max_drawdown(equity: np.ndarray) -> tuple[float, int]:
    """Return (max DD as positive percent, longest underwater duration in bars)."""
    if len(equity) == 0:
        return 0.0, 0
    peak = equity[0]
    max_dd = 0.0
    current_underwater = 0
    longest_underwater = 0
    for v in equity:
        if v >= peak:
            peak = v
            current_underwater = 0
        else:
            current_underwater += 1
            if current_underwater > longest_underwater:
                longest_underwater = current_underwater
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return float(max_dd), int(longest_underwater)


def annualized_return_pct(
    equity: np.ndarray, periods_per_year: int = TRADING_DAYS
) -> float:
    if len(equity) < 2 or equity[0] <= 0:
        return 0.0
    n_periods = len(equity) - 1
    total = equity[-1] / equity[0]
    if total <= 0:
        return -100.0
    return (total ** (periods_per_year / n_periods) - 1.0) * 100.0


def downside_deviation(
    returns: np.ndarray, periods_per_year: int = TRADING_DAYS
) -> float:
    """Annualized downside deviation (std of negative returns)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0:
        return 0.0
    return float(np.sqrt(np.mean(downside**2)) * math.sqrt(periods_per_year))


def compute_alpha_beta(
    strategy_returns: np.ndarray | None,
    benchmark_returns: np.ndarray | None,
    periods_per_year: int = TRADING_DAYS,
) -> AlphaBetaResult | None:
    """Annualized alpha / beta of strategy vs benchmark via statsmodels OLS.

    Fits ``r_strategy_t = alpha_daily + beta * r_benchmark_t + e_t`` on the
    raw daily return series (risk-free rate assumed 0). Standard errors come
    from HC1 heteroskedasticity-robust covariance (``cov_type='HC1'``), so
    the reported t-stats and p-values do not assume homoskedastic noise.

    Alpha and ``alpha_se`` are annualized and expressed in percent
    (multiplied by ``periods_per_year * 100``); the t-stat / p-value are
    unchanged by that linear rescaling. Beta is unitless.

    Edge cases:
      * ``benchmark_returns`` is None or empty → returns ``None`` so the
        caller can degrade gracefully (e.g. no benchmark configured).
      * Length mismatch between the two series → raises ``ValueError`` so
        a misalignment bug surfaces loudly.
      * Fewer than 2 observations, or a benchmark with zero variance →
        returns ``None`` (regression is undefined).
      * 2 ≤ n < 30 → still returns a result; the caller can flag the low
        ``n_obs`` if it wants to refuse to publish the t-stat.
    """
    if strategy_returns is None or benchmark_returns is None:
        return None

    s = np.asarray(strategy_returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)

    if s.size == 0 or b.size == 0:
        return None
    if s.shape != b.shape:
        raise ValueError(
            f"strategy_returns and benchmark_returns must have the same length; "
            f"got {s.shape} vs {b.shape}"
        )
    if s.size < 2:
        return None
    if not np.isfinite(s).all() or not np.isfinite(b).all():
        return None
    if float(np.var(b, ddof=1)) == 0.0:
        return None

    X = sm.add_constant(b, has_constant="add")
    try:
        model = sm.OLS(s, X).fit(cov_type="HC1")
    except Exception:
        return None

    daily_alpha = float(model.params[0])
    daily_alpha_se = float(model.bse[0])
    beta = float(model.params[1])
    beta_se = float(model.bse[1])

    scale = periods_per_year * 100.0
    return AlphaBetaResult(
        alpha=daily_alpha * scale,
        alpha_se=daily_alpha_se * scale,
        alpha_t=float(model.tvalues[0]),
        alpha_pvalue=float(model.pvalues[0]),
        beta=beta,
        beta_se=beta_se,
        beta_t=float(model.tvalues[1]),
        beta_pvalue=float(model.pvalues[1]),
        r_squared=float(model.rsquared),
        n_obs=int(model.nobs),
    )


# Back-compat shim: the legacy ``alpha_beta`` returned a bare ``(alpha, beta)``
# tuple. Keep the symbol available for any out-of-tree caller, delegating to
# the new richer implementation.
def alpha_beta(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    periods_per_year: int = TRADING_DAYS,
) -> tuple[float, float]:
    """Deprecated thin wrapper around :func:`compute_alpha_beta`.

    Returns just ``(alpha, beta)`` (annualized %) for backward compatibility.
    Returns ``(0.0, 0.0)`` when the regression is undefined, matching the
    historical behaviour of the previous hand-rolled OLS.
    """
    if strategy_returns is None or benchmark_returns is None:
        return 0.0, 0.0
    s = np.asarray(strategy_returns, dtype=np.float64)
    b = np.asarray(benchmark_returns, dtype=np.float64)
    n = min(s.size, b.size)
    if n < 2:
        return 0.0, 0.0
    res = compute_alpha_beta(s[-n:], b[-n:], periods_per_year)
    if res is None:
        return 0.0, 0.0
    return res.alpha, res.beta


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_returns: int,
    n_trials: int = 1,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Bailey & López de Prado (2014) Deflated Sharpe Ratio.

    Returns the probability that the *true* Sharpe exceeds zero, given the
    observed Sharpe and the number of strategies tested. Output in [0, 1];
    > 0.95 is roughly equivalent to "statistically significant after correcting
    for multiple-testing inflation".

    n_trials defaults to 1 (no deflation); pass the size of the parameter grid
    when reporting an optimized strategy.
    """
    if n_returns < 2 or observed_sharpe == 0.0:
        return 0.0

    # Expected max Sharpe under the null (Bailey & López de Prado, eq. 4)
    if n_trials <= 1:
        sr0 = 0.0
    else:
        emc = 0.5772156649  # Euler-Mascheroni
        z_inv = stats.norm.ppf(1.0 - 1.0 / n_trials)
        z_inv2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
        sr0 = (1.0 - emc) * z_inv + emc * z_inv2

    # Variance of the estimated Sharpe (eq. 9)
    sr_hat = observed_sharpe / math.sqrt(TRADING_DAYS)  # de-annualize
    sr0_periodic = sr0 / math.sqrt(TRADING_DAYS)
    denom = 1.0 - skew * sr_hat + ((kurtosis - 1) / 4.0) * sr_hat**2
    if denom <= 0 or n_returns <= 1:
        return 0.0
    var_sr = denom / (n_returns - 1)
    if var_sr <= 0:
        return 0.0
    z = (sr_hat - sr0_periodic) / math.sqrt(var_sr)
    return float(stats.norm.cdf(z))


def compute_all(
    equity: np.ndarray,
    benchmark_equity: np.ndarray | None = None,
    n_trials: int = 1,
    periods_per_year: int = TRADING_DAYS,
) -> PerformanceMetrics:
    """One-shot computation of every metric in PerformanceMetrics."""
    if len(equity) < 2:
        return PerformanceMetrics(0, 0, 0, 0, 0, 0, 0, 0, None, None, 0)

    rets = daily_returns(equity)
    total_ret = (equity[-1] / equity[0] - 1.0) * 100.0 if equity[0] > 0 else 0.0
    ann_ret = annualized_return_pct(equity, periods_per_year)
    sr = sharpe_ratio(rets, periods_per_year)
    so = sortino_ratio(rets, periods_per_year)
    mdd, mdd_dur = max_drawdown(equity)
    cm = calmar_ratio(ann_ret, mdd)
    dd_dev = downside_deviation(rets, periods_per_year)

    ab: AlphaBetaResult | None = None
    if benchmark_equity is not None and len(benchmark_equity) >= 2:
        bench_rets = daily_returns(benchmark_equity)
        # Align lengths defensively; compute_alpha_beta itself enforces equality
        # but compute_all has historically been forgiving of small mismatches.
        n = min(len(rets), len(bench_rets))
        if n >= 2:
            ab = compute_alpha_beta(rets[-n:], bench_rets[-n:], periods_per_year)

    skew = float(stats.skew(rets, bias=False)) if len(rets) > 2 else 0.0
    kurt = (
        float(stats.kurtosis(rets, fisher=False, bias=False)) if len(rets) > 3 else 3.0
    )
    dsr = deflated_sharpe_ratio(
        sr, len(rets), n_trials=n_trials, skew=skew, kurtosis=kurt
    )

    return PerformanceMetrics(
        total_return_pct=float(total_ret),
        annualized_return_pct=float(ann_ret),
        sharpe_ratio=float(sr),
        sortino_ratio=float(so),
        calmar_ratio=float(cm),
        max_drawdown_pct=float(mdd),
        max_drawdown_duration_bars=int(mdd_dur),
        downside_deviation=float(dd_dev),
        alpha=ab.alpha if ab is not None else None,
        beta=ab.beta if ab is not None else None,
        deflated_sharpe_ratio=float(dsr),
        alpha_se=ab.alpha_se if ab is not None else None,
        alpha_t=ab.alpha_t if ab is not None else None,
        alpha_pvalue=ab.alpha_pvalue if ab is not None else None,
        beta_se=ab.beta_se if ab is not None else None,
        beta_t=ab.beta_t if ab is not None else None,
        beta_pvalue=ab.beta_pvalue if ab is not None else None,
        r_squared=ab.r_squared if ab is not None else None,
        alpha_beta_n_obs=ab.n_obs if ab is not None else None,
    )
