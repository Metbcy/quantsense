from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    ticker: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None


@dataclass
class OrderResult:
    order_id: str
    status: OrderStatus
    filled_price: float
    filled_quantity: float
    timestamp: datetime
    message: str = ""


@dataclass
class PositionInfo:
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    market_value: float


@dataclass
class PortfolioSummary:
    total_value: float
    cash: float
    positions_value: float
    total_pnl: float
    total_pnl_pct: float
    positions: list[PositionInfo] = field(default_factory=list)
    daily_pnl: float = 0.0


class Broker(ABC):
    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_positions(self) -> list[PositionInfo]: ...

    @abstractmethod
    async def get_portfolio(self) -> PortfolioSummary: ...

    @abstractmethod
    async def get_trade_history(self) -> list[dict]: ...
