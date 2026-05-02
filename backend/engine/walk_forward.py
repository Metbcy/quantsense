"""Anchored walk-forward optimization.

The old optimizer was a Sharpe-overfitting machine: it picked the best
parameters across the *entire* sample and reported in-sample Sharpe as if it
were a real expectation. This module fixes that.

Anchored walk-forward:
  * Split the bar series into N contiguous windows.
  * For window k:
      - train_bars = bars[: end_of_window_k]    (anchored, growing)
      - test_bars  = bars[window_k : window_{k+1}]  (out-of-sample slice)
      - Grid-search params on `train_bars`, pick the best by `metric`.
      - Run those params on `test_bars`, record OOS metrics.
  * Aggregate IS vs OOS Sharpe. Big gap = overfit.

This is the standard "honest" backtest pattern in quant research and is
honest about overfitting risk.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import numpy as np

from data.provider import OHLCVBar

from .backtest import BacktestConfig, run_backtest
from .metrics import compute_all
from .strategy import STRATEGY_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    window_idx: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    best_params: dict[str, Any]
    is_sharpe: float
    oos_sharpe: float
    oos_return_pct: float
    oos_max_dd_pct: float
    oos_n_trades: int


@dataclass
class WalkForwardResult:
    ticker: str
    strategy_type: str
    n_windows: int
    grid_size: int
    windows: list[WalkForwardWindow]
    aggregate_is_sharpe: float
    aggregate_oos_sharpe: float
    sharpe_degradation: float  # IS - OOS, positive = overfit
    oos_equity_curve: list[tuple[date, float]]
    deflated_sharpe_ratio: float


def _grid(param_ranges: dict[str, dict]) -> list[dict[str, Any]]:
    """Expand a {name: {type, min, max, step | options}} dict to a list of dicts."""
    keys, value_lists = [], []
    for name, spec in param_ranges.items():
        keys.append(name)
        if spec.get("type") == "categorical":
            value_lists.append(list(spec["options"]))
        elif spec.get("type") == "int":
            step = int(spec.get("step") or 1)
            value_lists.append(list(range(int(spec["min"]), int(spec["max"]) + 1, step)))
        elif spec.get("type") == "float":
            step = float(spec.get("step") or 0.1)
            n = int((float(spec["max"]) - float(spec["min"])) / step) + 1
            value_lists.append([float(spec["min"]) + i * step for i in range(n)])
        else:
            raise ValueError(f"Unknown param type for {name}: {spec}")
    return [dict(zip(keys, combo)) for combo in itertools.product(*value_lists)]


def run_walk_forward(
    *,
    ticker: str,
    strategy_type: str,
    bars: list[OHLCVBar],
    param_ranges: dict[str, dict],
    n_windows: int = 5,
    train_test_ratio: float = 4.0,  # train is 4x as long as one test slice (anchored)
    initial_capital: float = 100_000.0,
    metric: str = "sharpe_ratio",
) -> WalkForwardResult:
    """Run an anchored walk-forward optimization.

    Args:
        bars: full OHLCV history.
        param_ranges: same shape the API expects (compatible with old optimizer).
        n_windows: number of OOS test windows.
        train_test_ratio: ignored for anchored mode but reserved for future
            rolling mode.
        metric: which metric to optimize on the IS slice (sharpe_ratio is
            standard).
    """
    strategy_cls = STRATEGY_REGISTRY.get(strategy_type)
    if not strategy_cls:
        raise ValueError(f"Strategy '{strategy_type}' not in registry")
    if len(bars) < 60:
        raise ValueError("Need at least 60 bars for walk-forward analysis")
    if n_windows < 2:
        raise ValueError("n_windows must be >= 2")

    grid = _grid(param_ranges)
    if not grid:
        raise ValueError("Empty param grid")

    # Reserve last 60% of data for OOS testing windows; first 40% is the
    # initial training anchor. Each test window is equal length within OOS.
    initial_train_n = max(int(len(bars) * 0.4), 30)
    oos_total = len(bars) - initial_train_n
    test_window_n = max(oos_total // n_windows, 5)
    if test_window_n < 5:
        raise ValueError("Test window size too small; reduce n_windows or use more data")

    windows: list[WalkForwardWindow] = []
    oos_equity: list[tuple[date, float]] = []
    rolling_capital = initial_capital
    is_sharpes: list[float] = []
    oos_returns: list[np.ndarray] = []  # daily-return arrays per window

    for k in range(n_windows):
        train_end_idx = initial_train_n + k * test_window_n
        test_start_idx = train_end_idx
        test_end_idx = min(train_end_idx + test_window_n, len(bars))
        if test_end_idx - test_start_idx < 5:
            break

        train_bars = bars[:train_end_idx]
        test_bars = bars[test_start_idx:test_end_idx]

        # In-sample grid search.
        best_params = None
        best_score = -float("inf")
        best_is_sharpe = 0.0
        for params in grid:
            try:
                strat = strategy_cls(params)
                cfg = BacktestConfig(
                    ticker=ticker,
                    strategy=strat,
                    start_date=train_bars[0].date,
                    end_date=train_bars[-1].date,
                    initial_capital=initial_capital,
                )
                res = run_backtest(cfg, train_bars)
                score = getattr(res.metrics, metric, res.metrics.sharpe_ratio)
                if score > best_score:
                    best_score = score
                    best_params = params
                    best_is_sharpe = res.metrics.sharpe_ratio
            except Exception as exc:
                logger.debug("WF train trial failed: %s", exc)
                continue

        if best_params is None:
            continue

        # Out-of-sample evaluation with the chosen params.
        strat = strategy_cls(best_params)
        cfg = BacktestConfig(
            ticker=ticker,
            strategy=strat,
            start_date=test_bars[0].date,
            end_date=test_bars[-1].date,
            initial_capital=rolling_capital,
        )
        oos = run_backtest(cfg, bars)  # pass full bars for indicator warm-up

        # Stitch OOS equity into the rolling curve.
        for d, v in oos.equity_curve:
            oos_equity.append((d, v))
        if oos.equity_curve:
            rolling_capital = oos.equity_curve[-1][1]
            oos_arr = np.array([v for _, v in oos.equity_curve], dtype=np.float64)
            if len(oos_arr) > 1:
                oos_returns.append(np.diff(oos_arr) / oos_arr[:-1])

        is_sharpes.append(best_is_sharpe)

        windows.append(
            WalkForwardWindow(
                window_idx=k,
                train_start=train_bars[0].date,
                train_end=train_bars[-1].date,
                test_start=test_bars[0].date,
                test_end=test_bars[-1].date,
                best_params=best_params,
                is_sharpe=float(best_is_sharpe),
                oos_sharpe=float(oos.metrics.sharpe_ratio),
                oos_return_pct=float(oos.metrics.total_return_pct),
                oos_max_dd_pct=float(oos.metrics.max_drawdown_pct),
                oos_n_trades=len([t for t in oos.trades if t.side == "sell"]),
            )
        )

    # Aggregate stats.
    agg_is = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    if oos_returns:
        all_oos = np.concatenate(oos_returns)
        from .metrics import sharpe_ratio
        agg_oos = sharpe_ratio(all_oos)
        # Deflated Sharpe: account for the size of the param grid.
        equity_oos = np.array([v for _, v in oos_equity], dtype=np.float64)
        full_metrics = compute_all(equity_oos, n_trials=len(grid))
        dsr = full_metrics.deflated_sharpe_ratio
    else:
        agg_oos = 0.0
        dsr = 0.0

    return WalkForwardResult(
        ticker=ticker,
        strategy_type=strategy_type,
        n_windows=len(windows),
        grid_size=len(grid),
        windows=windows,
        aggregate_is_sharpe=agg_is,
        aggregate_oos_sharpe=float(agg_oos),
        sharpe_degradation=float(agg_is - agg_oos),
        oos_equity_curve=oos_equity,
        deflated_sharpe_ratio=float(dsr),
    )


def to_dict(r: WalkForwardResult) -> dict:
    """JSON-friendly serialization for API responses."""
    return {
        "ticker": r.ticker,
        "strategy_type": r.strategy_type,
        "n_windows": r.n_windows,
        "grid_size": r.grid_size,
        "aggregate_is_sharpe": r.aggregate_is_sharpe,
        "aggregate_oos_sharpe": r.aggregate_oos_sharpe,
        "sharpe_degradation": r.sharpe_degradation,
        "deflated_sharpe_ratio": r.deflated_sharpe_ratio,
        "windows": [
            {
                **asdict(w),
                "train_start": w.train_start.isoformat(),
                "train_end": w.train_end.isoformat(),
                "test_start": w.test_start.isoformat(),
                "test_end": w.test_end.isoformat(),
            }
            for w in r.windows
        ],
        "oos_equity_curve": [
            {"date": d.isoformat(), "value": v} for d, v in r.oos_equity_curve
        ],
    }
