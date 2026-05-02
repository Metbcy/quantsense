"""Strategy parameter optimization — walk-forward only.

The previous version was a single-pass grid search over the full sample,
which (a) overstates performance and (b) is exactly the trap quant
interviewers test for. This module now wraps the walk-forward engine.
"""

from __future__ import annotations

import logging
from datetime import date

from data.provider import OHLCVBar

from .walk_forward import run_walk_forward, to_dict as wf_to_dict

logger = logging.getLogger(__name__)


def run_strategy_optimization(
    ticker: str,
    strategy_type: str,
    bars: list[OHLCVBar],
    start_date: date,
    end_date: date,
    param_ranges: dict,
    initial_capital: float = 100_000.0,
    n_trials: int = 50,  # legacy arg; mapped to n_windows when small
    metric: str = "sharpe_ratio",
) -> dict:
    """Walk-forward grid optimization.

    Maps the legacy `n_trials` arg to a sensible `n_windows` (default 5).
    Returns a JSON-friendly dict shaped for the walk-forward UI panel.
    """
    n_windows = 5 if n_trials >= 5 else max(2, n_trials)
    result = run_walk_forward(
        ticker=ticker,
        strategy_type=strategy_type,
        bars=bars,
        param_ranges=param_ranges,
        n_windows=n_windows,
        initial_capital=initial_capital,
        metric=metric,
    )
    return wf_to_dict(result)
