"""Background scheduler for periodic sentiment refresh."""

import asyncio
import logging
from datetime import datetime

from sentiment.aggregator import create_aggregator, SentimentAggregator

logger = logging.getLogger(__name__)


class SentimentScheduler:
    """Runs sentiment analysis on watchlist tickers at a configurable interval."""

    def __init__(self, interval_minutes: int = 30):
        self.interval_minutes = interval_minutes
        self.aggregator: SentimentAggregator | None = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._watchlist: list[str] = []

    def update_watchlist(self, tickers: list[str]):
        self._watchlist = tickers

    def update_interval(self, minutes: int):
        self.interval_minutes = max(5, minutes)

    async def start(self):
        if self._running:
            return
        self._running = True
        self.aggregator = create_aggregator()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Sentiment scheduler started (interval=%dm)", self.interval_minutes)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Sentiment scheduler stopped")

    async def _run_loop(self):
        while self._running:
            try:
                await self._refresh_all()
            except Exception as e:
                logger.error("Sentiment refresh error: %s", e)
            await asyncio.sleep(self.interval_minutes * 60)

    async def _refresh_all(self):
        if not self._watchlist or not self.aggregator:
            return

        logger.info("Refreshing sentiment for %d tickers", len(self._watchlist))
        results = []
        for ticker in self._watchlist:
            try:
                result = await self.aggregator.analyze_ticker(ticker)
                results.append(result)
                logger.info(
                    "Sentiment for %s: %.2f (%s)",
                    ticker,
                    result.overall_score,
                    result.trend,
                )
            except Exception as e:
                logger.warning("Failed to analyze %s: %s", ticker, e)

        return results

    async def analyze_single(self, ticker: str):
        if not self.aggregator:
            self.aggregator = create_aggregator()
        return await self.aggregator.analyze_ticker(ticker)


# Module-level singleton
scheduler = SentimentScheduler()
