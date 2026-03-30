"""QuantSense backtesting engine."""

from .backtest import (
    BacktestConfig,
    BacktestMetrics,
    BacktestResult,
    BacktestTradeRecord,
    run_backtest,
)
from .screener import ScreenerResult, screen_tickers
from .strategy import (
    STRATEGY_REGISTRY,
    BollingerBandStrategy,
    MACDStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    SentimentMomentumStrategy,
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
    "MACDStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "STRATEGY_REGISTRY",
    "ScreenerResult",
    "SentimentMomentumStrategy",
    "Signal",
    "SignalType",
    "Strategy",
    "run_backtest",
    "screen_tickers",
]