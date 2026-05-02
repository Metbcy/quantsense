"""Quant-grade performance metrics.

Goes beyond textbook Sharpe to provide the metrics that matter in practice:
  * Sortino ratio (downside-only volatility)
  * Calmar ratio (return / max DD)
  * Max drawdown depth AND duration (in bars)
  * Annualized return + downside deviation
  * Alpha & beta vs a benchmark series
  * Deflated Sharpe Ratio (Bailey & López de Prado, 2014) — adjusts the
    observed Sharpe for selection bias when many strategies have been tried.

All functions are pure: take numpy arrays / lists of floats and return floats.
No dependence on `BacktestResult` so they are reusable from walk-forward
analysis, optimization, and significance testing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

TRADING_DAYS = 252


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
    alpha: float | None  # annualized; None if no benchmark provided
    beta: float | None
    deflated_sharpe_ratio: float


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
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
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


def downside_deviation(returns: np.ndarray, periods_per_year: int = TRADING_DAYS) -> float:
    """Annualized downside deviation (std of negative returns)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) == 0:
        return 0.0
    return float(np.sqrt(np.mean(downside ** 2)) * math.sqrt(periods_per_year))


def alpha_beta(
    strategy_returns: np.ndarray,
    benchmark_returns: np.ndarray,
    periods_per_year: int = TRADING_DAYS,
) -> tuple[float, float]:
    """Annualized alpha (%) and beta vs benchmark via OLS on excess returns.

    Risk-free rate assumed 0 for simplicity.
    """
    n = min(len(strategy_returns), len(benchmark_returns))
    if n < 5:
        return 0.0, 0.0
    s = strategy_returns[-n:]
    b = benchmark_returns[-n:]
    var_b = float(np.var(b, ddof=1))
    if var_b == 0.0:
        return 0.0, 0.0
    cov = float(np.cov(s, b, ddof=1)[0, 1])
    beta = cov / var_b
    daily_alpha = float(np.mean(s) - beta * np.mean(b))
    alpha_annual_pct = daily_alpha * periods_per_year * 100.0
    return float(alpha_annual_pct), float(beta)


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
    denom = 1.0 - skew * sr_hat + ((kurtosis - 1) / 4.0) * sr_hat ** 2
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

    alpha, beta = (None, None)
    if benchmark_equity is not None and len(benchmark_equity) >= 2:
        bench_rets = daily_returns(benchmark_equity)
        a, b = alpha_beta(rets, bench_rets, periods_per_year)
        alpha, beta = a, b

    skew = float(stats.skew(rets, bias=False)) if len(rets) > 2 else 0.0
    kurt = float(stats.kurtosis(rets, fisher=False, bias=False)) if len(rets) > 3 else 3.0
    dsr = deflated_sharpe_ratio(sr, len(rets), n_trials=n_trials, skew=skew, kurtosis=kurt)

    return PerformanceMetrics(
        total_return_pct=float(total_ret),
        annualized_return_pct=float(ann_ret),
        sharpe_ratio=float(sr),
        sortino_ratio=float(so),
        calmar_ratio=float(cm),
        max_drawdown_pct=float(mdd),
        max_drawdown_duration_bars=int(mdd_dur),
        downside_deviation=float(dd_dev),
        alpha=alpha,
        beta=beta,
        deflated_sharpe_ratio=float(dsr),
    )
