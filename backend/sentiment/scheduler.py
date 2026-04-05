"""Background sentiment refresh using APScheduler.

Wired into the FastAPI lifespan so it starts/stops with the app.
Reads the watchlist from the DB each cycle, runs the full sentiment
pipeline, and persists results — exactly like the manual /analyze endpoint.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import get_settings
from models.database import SessionLocal
from models.schemas import SentimentAggregate, SentimentRecord, Watchlist
from sentiment.aggregator import create_aggregator

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _refresh_watchlist_sentiment() -> None:
    """Analyze sentiment for every ticker in the watchlist."""
    db = SessionLocal()
    try:
        tickers = [w.ticker for w in db.query(Watchlist).all()]
        if not tickers:
            logger.debug("Sentiment scheduler: watchlist empty, skipping")
            return

        logger.info("Sentiment scheduler: refreshing %d tickers", len(tickers))
        aggregator = create_aggregator()

        for ticker in tickers:
            try:
                result = await aggregator.analyze_ticker(ticker)

                for item in result.headlines:
                    db.add(SentimentRecord(
                        ticker=ticker,
                        source=item.get("source", "unknown"),
                        headline=item.get("headline", ""),
                        snippet=None,
                        vader_score=item.get("score", 0.0),
                        llm_score=result.llm_score,
                        llm_summary=None,
                    ))

                existing = (
                    db.query(SentimentAggregate)
                    .filter(SentimentAggregate.ticker == ticker)
                    .first()
                )
                if existing:
                    existing.score = result.overall_score
                    existing.trend = result.trend
                    existing.num_sources = result.num_sources
                else:
                    db.add(SentimentAggregate(
                        ticker=ticker,
                        score=result.overall_score,
                        trend=result.trend,
                        num_sources=result.num_sources,
                    ))

                db.commit()
                logger.info(
                    "Sentiment refreshed: %s score=%.3f (%d sources)",
                    ticker, result.overall_score, result.num_sources,
                )
            except Exception:
                db.rollback()
                logger.exception("Sentiment refresh failed for %s", ticker)
    finally:
        db.close()


def start_scheduler() -> AsyncIOScheduler:
    """Start the background sentiment scheduler. Call once at app startup."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    settings = get_settings()
    interval = settings.SENTIMENT_REFRESH_MINUTES

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _refresh_watchlist_sentiment,
        "interval",
        minutes=interval,
        id="sentiment_refresh",
        name=f"Sentiment refresh (every {interval}m)",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Sentiment scheduler started (interval=%dm)", interval)
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Sentiment scheduler stopped")
