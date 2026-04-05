"""Auto-trading API endpoints."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.database import get_db
from models.schemas import Watchlist
from trading.auto_trader import AutoTrader
from api.trading import _get_active_broker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/run")
async def run_auto_trade(
    buy_threshold: float = 0.15,
    sell_threshold: float = -0.15,
    db: Session = Depends(get_db),
):
    """Run one autonomous trading cycle across the watchlist."""
    watchlist = db.query(Watchlist).all()
    tickers = [w.ticker for w in watchlist]

    if not tickers:
        return {"error": "No tickers in watchlist. Add tickers in Settings first."}

    broker = _get_active_broker(db)
    trader = AutoTrader(broker=broker, buy_threshold=buy_threshold, sell_threshold=sell_threshold)

    try:
        result = await trader.run_cycle(tickers)
        # Persist trades made by auto-trader
        from api.trading import _save_broker_to_db
        _save_broker_to_db(db)
        return result
    except Exception as exc:
        logger.exception("Auto-trade cycle failed")
        return {"error": f"Auto-trade cycle failed: {str(exc)}"}


@router.post("/analyze")
async def analyze_only(
    buy_threshold: float = 0.15,
    sell_threshold: float = -0.15,
    db: Session = Depends(get_db),
):
    """Analyze watchlist tickers without executing trades."""
    watchlist = db.query(Watchlist).all()
    tickers = [w.ticker for w in watchlist]

    if not tickers:
        return {"error": "No tickers in watchlist. Add tickers in Settings first."}

    broker = _get_active_broker(db)
    trader = AutoTrader(broker=broker, buy_threshold=buy_threshold, sell_threshold=sell_threshold)

    analyses = []
    for ticker in tickers:
        try:
            analysis = await trader.analyze_ticker(ticker)
            analyses.append({
                "ticker": analysis.ticker,
                "price": analysis.price,
                "sentiment_score": analysis.sentiment_score,
                "rsi": analysis.rsi_value,
                "sma_20": analysis.sma_20,
                "signal": analysis.signal,
                "confidence": analysis.confidence,
                "reasons": analysis.reasons,
            })
        except Exception as e:
            analyses.append({
                "ticker": ticker,
                "signal": "error",
                "confidence": 0,
                "reasons": [str(e)],
            })

    return {"analyses": analyses}
