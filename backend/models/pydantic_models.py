from datetime import datetime, date
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field


# ── Watchlist / Ticker ──────────────────────────────────────────────

class TickerCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    name: Optional[str] = Field(None, max_length=200)


class TickerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    name: Optional[str] = None
    added_at: datetime


# ── OHLCV ───────────────────────────────────────────────────────────

class OHLCVResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    provider: str


# ── Sentiment ───────────────────────────────────────────────────────

class SentimentFeedItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    headline: str
    snippet: Optional[str] = None
    vader_score: float
    llm_score: Optional[float] = None
    llm_summary: Optional[str] = None
    created_at: datetime


class SentimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    score: float
    trend: str
    num_sources: int
    updated_at: datetime


class SentimentHistoryResponse(BaseModel):
    ticker: str
    items: list[SentimentFeedItem] = []
    aggregate: Optional[SentimentResponse] = None


# ── Strategy ────────────────────────────────────────────────────────

class StrategyCreate(BaseModel):
    name: str
    type: str
    params: dict = {}


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    params: dict
    created_at: datetime


# ── Backtest ────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    ticker: str
...
    atr_stop_multiplier: Optional[float] = Field(None, ge=0, le=10.0)


# ── Optimization ───────────────────────────────────────────────────

class ParamRange(BaseModel):
    min: float
    max: float
    step: Optional[float] = None
    type: str = "int" # "int", "float", "categorical"
    options: Optional[list[Any]] = None

class OptimizeRequest(BaseModel):
    ticker: str
    strategy_type: str
    start_date: date
    end_date: date
    initial_capital: float = 100000.0
    param_ranges: dict[str, ParamRange]
    n_trials: int = 50
    metric: str = "sharpe_ratio" # "total_return_pct", "sharpe_ratio", "win_rate"

class OptimizationTrial(BaseModel):
    params: dict
    metrics: dict
    trial_id: int

class OptimizationResponse(BaseModel):
    best_params: dict
    best_value: float
    metric: str
    trials: list[OptimizationTrial]


# ── Webhooks ────────────────────────────────────────────────────────

class TradingViewWebhook(BaseModel):
    secret: str
    ticker: str
    action: str # "buy", "sell"
    quantity: float
    order_type: str = "market"
    price: Optional[float] = None


class BacktestTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    side: str
    price: float
    quantity: float
    value: float
    pnl: float


class BacktestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    ticker: str
    start_date: date
    end_date: date
    initial_capital: float
    final_value: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    created_at: datetime
    trades: list[BacktestTradeResponse] = []


# ── Portfolio ───────────────────────────────────────────────────────

class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    unrealized_pnl: float
    updated_at: datetime


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cash: float
    initial_cash: float
    created_at: datetime
    positions: list[PositionResponse] = []


# ── Trading / Orders ───────────────────────────────────────────────

class OrderRequest(BaseModel):
    ticker: str
    side: str
    order_type: str = "market"
    price: Optional[float] = Field(None, gt=0)
    quantity: float = Field(..., gt=0)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    side: str
    order_type: str
    price: float
    quantity: float
    value: float
    status: str
    created_at: datetime


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    portfolio_id: int
    ticker: str
    side: str
    order_type: str
    price: float
    quantity: float
    value: float
    strategy_name: Optional[str] = None
    sentiment_score: Optional[float] = None
    status: str
    created_at: datetime


# ── Settings ────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    key: str
    value: str


class SettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str
