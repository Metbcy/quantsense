from datetime import date

import httpx

from config.settings import settings
from data.provider import DataProvider, OHLCVBar, Quote, TickerInfo

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageProvider(DataProvider):
    """Data provider backed by Alpha Vantage REST API. Requires API key."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.ALPHA_VANTAGE_API_KEY or ""

    async def get_ohlcv(
        self, ticker: str, start: date, end: date, interval: str = "1d"
    ) -> list[OHLCVBar]:
        if not self.api_key:
            return []

        function = "TIME_SERIES_DAILY" if interval in ("1d", "daily") else "TIME_SERIES_DAILY"
        params = {
            "function": function,
            "symbol": ticker,
            "outputsize": "full",
            "apikey": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            time_series = data.get("Time Series (Daily)", {})
            if not time_series:
                return []

            bars: list[OHLCVBar] = []
            for date_str, values in sorted(time_series.items()):
                bar_date = date.fromisoformat(date_str)
                if bar_date < start or bar_date > end:
                    continue
                bars.append(
                    OHLCVBar(
                        date=bar_date,
                        open=float(values["1. open"]),
                        high=float(values["2. high"]),
                        low=float(values["3. low"]),
                        close=float(values["4. close"]),
                        volume=int(values["5. volume"]),
                    )
                )
            return bars
        except Exception:
            return []

    async def get_quote(self, ticker: str) -> Quote:
        if not self.api_key:
            return Quote(
                ticker=ticker.upper(), price=0.0, change=0.0,
                change_percent=0.0, volume=0,
            )

        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": ticker,
            "apikey": self.api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(_BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            gq = data.get("Global Quote", {})
            if not gq:
                return Quote(
                    ticker=ticker.upper(), price=0.0, change=0.0,
                    change_percent=0.0, volume=0,
                )

            change_pct_str = gq.get("10. change percent", "0%").replace("%", "")
            return Quote(
                ticker=gq.get("01. symbol", ticker).upper(),
                price=float(gq.get("05. price", 0)),
                change=float(gq.get("09. change", 0)),
                change_percent=float(change_pct_str),
                volume=int(gq.get("06. volume", 0)),
            )
        except Exception:
            return Quote(
                ticker=ticker.upper(), price=0.0, change=0.0,
                change_percent=0.0, volume=0,
            )

    async def search_ticker(self, query: str) -> list[TickerInfo]:
        return []
