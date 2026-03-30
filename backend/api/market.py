"""Market data endpoints – quotes, OHLCV, search, screener."""

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from data.yahoo_provider import YahooFinanceProvider
from engine.screener import screen_tickers
from models.database import get_db
from models.schemas import Watchlist

logger = logging.getLogger(__name__)

router = APIRouter()
provider = YahooFinanceProvider()


@router.get("/search")
async def search(q: str = Query(..., min_length=1, description="Search query")):
    """Search for tickers matching query string."""
    try:
        results = await provider.search_ticker(q)
        return [
            {
                "ticker": r.ticker,
                "name": r.name,
                "exchange": r.exchange,
                "asset_type": r.asset_type,
            }
            for r in results
        ]
    except Exception as exc:
        logger.exception("Ticker search failed for q=%s", q)
        raise HTTPException(status_code=500, detail="Ticker search failed")


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get a real-time quote for a ticker."""
    try:
        quote = await provider.get_quote(ticker)
        return {
            "ticker": quote.ticker,
            "price": quote.price,
            "change": quote.change,
            "change_percent": quote.change_percent,
            "volume": quote.volume,
            "market_cap": quote.market_cap,
            "name": quote.name,
        }
    except Exception as exc:
        logger.exception("Quote fetch failed for %s", ticker)
        raise HTTPException(status_code=500, detail="Failed to fetch quote")


@router.get("/ohlcv/{ticker}")
async def get_ohlcv(
    ticker: str,
    start: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str = Query(None, description="End date (YYYY-MM-DD)"),
    interval: str = Query("1d", description="Bar interval (1d, 1wk, 1mo)"),
):
    """Get OHLCV bars for a ticker."""
    try:
        end_date = date.fromisoformat(end) if end else date.today()
        start_date = date.fromisoformat(start) if start else end_date - timedelta(days=365)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    try:
        bars = await provider.get_ohlcv(ticker, start_date, end_date, interval)
        return [
            {
                "date": b.date.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    except Exception as exc:
        logger.exception("OHLCV fetch failed for %s", ticker)
        raise HTTPException(status_code=500, detail="Failed to fetch OHLCV data")


@router.get("/screener")
async def run_screener(db: Session = Depends(get_db)):
    """Screen all watchlist tickers and return scored results."""
    watchlist = db.query(Watchlist).all()
    if not watchlist:
        return []

    tickers = [w.ticker for w in watchlist]
    try:
        results = await screen_tickers(tickers, provider)
        return [
            {
                "ticker": r.ticker,
                "price": r.price,
                "rsi": r.rsi,
                "sma_20": r.sma_20,
                "sentiment": r.sentiment,
                "signal": r.signal,
                "score": r.score,
            }
            for r in results
        ]
    except Exception as exc:
        logger.exception("Screener failed")
        raise HTTPException(status_code=500, detail="Screener execution failed")
