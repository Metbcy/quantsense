import asyncio
import logging
from datetime import date
from typing import Any

import yfinance as yf

from data.provider import DataProvider, OHLCVBar, Quote, TickerInfo
from data.utils import retry_async

logger = logging.getLogger(__name__)


EXTERNAL_TIMEOUT = 30  # seconds for external API calls


class YahooFinanceProvider(DataProvider):
    """Data provider backed by yfinance."""

    @retry_async(retries=3, delay=1.0, backoff=2.0)
    async def _fetch_ohlcv(self, ticker: str, start: date, end: date, interval: str) -> Any:
        return await asyncio.wait_for(
            asyncio.to_thread(
                lambda: yf.download(
                    ticker,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    interval=interval,
                    progress=False,
                    auto_adjust=True,
                )
            ),
            timeout=EXTERNAL_TIMEOUT,
        )

    async def get_ohlcv(
        self, ticker: str, start: date, end: date, interval: str = "1d"
    ) -> list[OHLCVBar]:
        try:
            df = await self._fetch_ohlcv(ticker, start, end, interval)
            if df is None or (hasattr(df, "empty") and df.empty):
                return []

            # yfinance may return MultiIndex columns for single tickers
            if hasattr(df, "columns") and isinstance(df.columns, __import__('pandas').MultiIndex):
                df.columns = df.columns.get_level_values(0)

            bars: list[OHLCVBar] = []
            for idx, row in df.iterrows():
                bars.append(
                    OHLCVBar(
                        date=idx.date() if hasattr(idx, "date") else idx,
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=int(row["Volume"]),
                    )
                )
            return bars
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {ticker} via Yahoo: {e}")
            return []

    @retry_async(retries=3, delay=1.0)
    async def _fetch_info(self, ticker: str) -> dict:
        async def _do():
            t = await asyncio.to_thread(lambda: yf.Ticker(ticker))
            return await asyncio.to_thread(lambda: t.info)
        return await asyncio.wait_for(_do(), timeout=EXTERNAL_TIMEOUT)

    async def get_quote(self, ticker: str) -> Quote:
        try:
            info = await self._fetch_info(ticker)
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0.0)
            prev = info.get("previousClose") or info.get("regularMarketPreviousClose", 0.0)
            change = price - prev if price and prev else 0.0
            change_pct = (change / prev * 100) if prev else 0.0
            return Quote(
                ticker=ticker.upper(),
                price=float(price or 0.0),
                change=round(change, 4),
                change_percent=round(change_pct, 4),
                volume=int(info.get("volume") or info.get("regularMarketVolume") or 0),
                market_cap=info.get("marketCap"),
                name=info.get("shortName") or info.get("longName"),
            )
        except Exception as e:
            logger.error(f"Error fetching quote for {ticker} via Yahoo: {e}")
            return Quote(
                ticker=ticker.upper(),
                price=0.0,
                change=0.0,
                change_percent=0.0,
                volume=0,
            )

    async def search_ticker(self, query: str) -> list[TickerInfo]:
        try:
            results: list[TickerInfo] = []
            search = await asyncio.wait_for(
                asyncio.to_thread(lambda: yf.Ticker(query)), timeout=EXTERNAL_TIMEOUT
            )
            info = await asyncio.wait_for(
                asyncio.to_thread(lambda: search.info), timeout=EXTERNAL_TIMEOUT
            )
            if info and info.get("symbol"):
                results.append(
                    TickerInfo(
                        ticker=info["symbol"],
                        name=info.get("shortName") or info.get("longName", query),
                        exchange=info.get("exchange"),
                        asset_type=info.get("quoteType"),
                    )
                )
            return results
        except Exception:
            return []
