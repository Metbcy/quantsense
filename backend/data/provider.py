from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class OHLCVBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Quote:
    ticker: str
    price: float
    change: float
    change_percent: float
    volume: int
    market_cap: Optional[float] = None
    name: Optional[str] = None


@dataclass
class TickerInfo:
    ticker: str
    name: str
    exchange: Optional[str] = None
    asset_type: Optional[str] = None


class DataProvider(ABC):
    @abstractmethod
    async def get_ohlcv(
        self, ticker: str, start: date, end: date, interval: str = "1d"
    ) -> list[OHLCVBar]:
        ...

    @abstractmethod
    async def get_quote(self, ticker: str) -> Quote:
        ...

    @abstractmethod
    async def search_ticker(self, query: str) -> list[TickerInfo]:
        ...
