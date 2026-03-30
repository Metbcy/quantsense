"""Sentiment analysis endpoints – analyze, feed, history."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db
from models.pydantic_models import SentimentHistoryResponse, SentimentResponse
from models.schemas import SentimentAggregate, SentimentRecord
from sentiment.aggregator import create_aggregator

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/analyze/{ticker}")
async def analyze_ticker(ticker: str, db: Session = Depends(get_db)):
    """Run full sentiment analysis for a ticker (fetch news, score, aggregate)."""
    try:
        aggregator = create_aggregator()
        result = await aggregator.analyze_ticker(ticker.upper())
    except Exception as exc:
        logger.exception("Sentiment analysis failed for %s", ticker)
        raise HTTPException(status_code=500, detail="Sentiment analysis failed")

    # Save individual headline records
    for item in result.headlines:
        record = SentimentRecord(
            ticker=ticker.upper(),
            source=item.get("source", "unknown"),
            headline=item.get("headline", ""),
            snippet=None,
            vader_score=item.get("score", 0.0),
            llm_score=result.llm_score,
            llm_summary=None,
        )
        db.add(record)

    # Upsert aggregate
    existing = (
        db.query(SentimentAggregate)
        .filter(SentimentAggregate.ticker == ticker.upper())
        .first()
    )
    if existing:
        existing.score = result.overall_score
        existing.trend = result.trend
        existing.num_sources = result.num_sources
    else:
        aggregate = SentimentAggregate(
            ticker=ticker.upper(),
            score=result.overall_score,
            trend=result.trend,
            num_sources=result.num_sources,
        )
        db.add(aggregate)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to save sentiment data")

    return {
        "ticker": ticker.upper(),
        "overall_score": result.overall_score,
        "vader_avg": result.vader_avg,
        "llm_score": result.llm_score,
        "trend": result.trend,
        "num_sources": result.num_sources,
        "updated_at": __import__("datetime").datetime.now().isoformat(),
        "headlines": [
            {
                **h,
                "published_at": h.get("published_at", __import__("datetime").datetime.now().isoformat()),
            }
            for h in result.headlines
        ],
    }


@router.get("/feed")
async def sentiment_feed(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get recent sentiment records across all tickers."""
    limit = min(max(1, limit), 500)
    records = (
        db.query(SentimentRecord)
        .order_by(SentimentRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "source": r.source,
            "headline": r.headline,
            "snippet": r.snippet,
            "vader_score": r.vader_score,
            "llm_score": r.llm_score,
            "llm_summary": r.llm_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@router.get("/history/{ticker}")
async def sentiment_history(ticker: str, db: Session = Depends(get_db)):
    """Get historical sentiment data for a specific ticker."""
    records = (
        db.query(SentimentRecord)
        .filter(SentimentRecord.ticker == ticker.upper())
        .order_by(SentimentRecord.created_at.desc())
        .all()
    )
    aggregate = (
        db.query(SentimentAggregate)
        .filter(SentimentAggregate.ticker == ticker.upper())
        .first()
    )

    return [
        {
            "date": r.created_at.isoformat() if r.created_at else None,
            "score": r.vader_score,
        }
        for r in records
    ]
