import logging
import optuna
from datetime import date
from typing import Dict, Any

from .backtest import run_backtest, BacktestConfig
from .strategy import STRATEGY_REGISTRY
from data.provider import OHLCVBar

logger = logging.getLogger(__name__)

def run_strategy_optimization(
    ticker: str,
    strategy_type: str,
    bars: list[OHLCVBar],
    start_date: date,
    end_date: date,
    param_ranges: dict,
    initial_capital: float = 100000.0,
    n_trials: int = 50,
    metric: str = "sharpe_ratio"
) -> dict:
    """
    Optimizes strategy parameters using Optuna.
    """
    strategy_cls = STRATEGY_REGISTRY.get(strategy_type)
    if not strategy_cls:
        raise ValueError(f"Strategy {strategy_type} not found")

    trials_data = []

    def objective(trial: optuna.Trial):
        # 1. Suggest parameters based on ranges
        params = {}
        for p_name, p_range in param_ranges.items():
            if p_range["type"] == "int":
                params[p_name] = trial.suggest_int(p_name, int(p_range["min"]), int(p_range["max"]), step=int(p_range.get("step") or 1))
            elif p_range["type"] == "float":
                params[p_name] = trial.suggest_float(p_name, float(p_range["min"]), float(p_range["max"]), step=float(p_range.get("step") or 0.1))
            elif p_range["type"] == "categorical":
                params[p_name] = trial.suggest_categorical(p_name, p_range["options"])

        # 2. Run backtest
        strategy = strategy_cls(params)
        config = BacktestConfig(
            ticker=ticker,
            strategy=strategy,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital
        )
        
        try:
            result = run_backtest(config, bars)
            metrics = result.metrics
            
            # Record trial
            trials_data.append({
                "trial_id": trial.number,
                "params": params,
                "metrics": {
                    "total_return_pct": metrics.total_return_pct,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "win_rate": metrics.win_rate,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                    "profit_factor": metrics.profit_factor,
                    "final_value": metrics.final_value
                }
            })

            # Return value to optimize (Optuna minimizes by default, but we'll use study.optimize(direction="maximize"))
            if metric == "sharpe_ratio":
                return metrics.sharpe_ratio
            elif metric == "total_return_pct":
                return metrics.total_return_pct
            elif metric == "win_rate":
                return metrics.win_rate
            return metrics.sharpe_ratio
        except Exception as e:
            logger.error(f"Trial {trial.number} failed: {e}")
            return -9999.0

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)

    return {
        "best_params": study.best_params,
        "best_value": study.best_value,
        "metric": metric,
        "trials": trials_data
    }
