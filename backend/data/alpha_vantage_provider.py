import logging
from datetime import date

import httpx

from config.settings import settings
from data.provider import DataProvider, OHLCVBar, Quote, TickerInfo
from data.utils import retry_async

_BASE_URL = "https://www.alphavantage.co/query"

logger = logging.getLogger(__name__)


class AlphaVantageProvider(DataProvider):
    """Data provider backed by Alpha Vantage REST API. Requires API key."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.ALPHA_VANTAGE_API_KEY or ""

    @retry_async(retries=3, delay=1.0, backoff=2.0)
    async def _fetch(self, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(_BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()

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
            data = await self._fetch(params)
            time_series = data.get("Time Series (Daily)", {})
            if not time_series:
                logger.warning(f"No daily time series found for {ticker} in AlphaVantage response")
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
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {ticker} via AlphaVantage: {e}")
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
            data = await self._fetch(params)
            gq = data.get("Global Quote", {})
            if not gq:
                logger.warning(f"No global quote found for {ticker} in AlphaVantage response")
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
        except Exception as e:
            logger.error(f"Error fetching quote for {ticker} via AlphaVantage: {e}")
            return Quote(
                ticker=ticker.upper(), price=0.0, change=0.0,
                change_percent=0.0, volume=0,
            )

    async def search_ticker(self, query: str) -> list[TickerInfo]:
        if not self.api_key:
            return []

        params = {
            "function": "SYMBOL_SEARCH",
            "keywords": query,
            "apikey": self.api_key,
        }

        try:
            data = await self._fetch(params)
            best_matches = data.get("bestMatches", [])
            results: list[TickerInfo] = []
            for match in best_matches:
                results.append(
                    TickerInfo(
                        ticker=match.get("1. symbol", ""),
                        name=match.get("2. name", ""),
                        exchange=match.get("4. region", ""),
                        asset_type=match.get("3. type", ""),
                    )
                )
            return results
        except Exception as e:
            logger.error(f"Error searching ticker {query} via AlphaVantage: {e}")
            return []
