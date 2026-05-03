"""QuantSense backtesting engine."""

from .backtest import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTradeRecord,
    run_backtest,
)
from .run_hash import CODE_VERSION, compute_run_hash, seed_from_run_hash
from .screener import ScreenerResult, screen_tickers
from .strategy import (
    STRATEGY_REGISTRY,
    BollingerBandStrategy,
    MACDStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    Signal,
    SignalType,
    Strategy,
)

__all__ = [
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestResult",
    "BacktestTradeRecord",
    "BollingerBandStrategy",
    "CODE_VERSION",
    "MACDStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "STRATEGY_REGISTRY",
    "ScreenerResult",
    "Signal",
    "SignalType",
    "Strategy",
    "compute_run_hash",
    "run_backtest",
    "screen_tickers",
    "seed_from_run_hash",
]
