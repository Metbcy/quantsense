"""Auto-trading API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import get_settings
from models.database import get_db, SessionLocal
from models.schemas import Watchlist
from trading.auto_trader import AutoTrader
from trading.risk_manager import RiskManager, RiskLimits
from trading.scheduler import get_scheduler_status, start_scheduler, stop_scheduler
from api.trading import _get_active_broker

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Scheduler models ──────────────────────────────────────────────────────────

class SchedulerStartRequest(BaseModel):
    interval_minutes: Optional[int] = None


# ── Scheduler endpoints ───────────────────────────────────────────────────────

@router.post("/scheduler/start")
async def scheduler_start(body: SchedulerStartRequest = SchedulerStartRequest()):
    """Start the auto-trade scheduler."""
    settings = get_settings()
    interval = body.interval_minutes or settings.AUTO_TRADE_INTERVAL_MINUTES
    start_scheduler(
        interval_minutes=interval,
        broker_factory=_get_active_broker,
        db_session_factory=SessionLocal,
    )
    return get_scheduler_status()


@router.post("/scheduler/stop")
async def scheduler_stop():
    """Stop the auto-trade scheduler."""
    stop_scheduler()
    return get_scheduler_status()


@router.get("/scheduler/status")
async def scheduler_status():
    """Get auto-trade scheduler status."""
    return get_scheduler_status()


@router.post("/run")
async def run_auto_trade(
    buy_threshold: float = 0.15,
    sell_threshold: float = -0.15,
    trailing_stop_pct: float | None = None,
    take_profit_pct: float | None = None,
    db: Session = Depends(get_db),
):
    """Run one autonomous trading cycle across the watchlist."""
    watchlist = db.query(Watchlist).all()
    tickers = [w.ticker for w in watchlist]

    if not tickers:
        return {"error": "No tickers in watchlist. Add tickers in Settings first."}

    broker = _get_active_broker(db)
    risk_manager = RiskManager(
        RiskLimits(
            trailing_stop_pct=trailing_stop_pct,
            take_profit_pct=take_profit_pct,
        )
    )
    trader = AutoTrader(
        broker=broker,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        risk_manager=risk_manager,
    )

    try:
        result = await trader.run_cycle(tickers)
        # Persist trades made by auto-trader
        from api.trading import _save_broker_to_db
        _save_broker_to_db(db)
        return result
    except Exception as exc:
        logger.exception("Auto-trade cycle failed")
        return {"error": f"Auto-trade cycle failed: {str(exc)}"}


@router.post("/rebalance")
async def rebalance_portfolio(
    threshold_pct: float = 0.05,
    db: Session = Depends(get_db),
):
    """Rebalance portfolio to equal-weight across all held positions."""
    broker = _get_active_broker(db)
    risk_manager = RiskManager(RiskLimits())
    trader = AutoTrader(broker=broker, risk_manager=risk_manager)

    try:
        result = await trader.rebalance(threshold_pct=threshold_pct)
        from api.trading import _save_broker_to_db
        _save_broker_to_db(db)
        return result
    except Exception as exc:
        logger.exception("Rebalance failed")
        return {"error": f"Rebalance failed: {str(exc)}"}


@router.post("/analyze")
async def analyze_only(
    buy_threshold: float = 0.15,
    sell_threshold: float = -0.15,
    trailing_stop_pct: float | None = None,
    take_profit_pct: float | None = None,
    db: Session = Depends(get_db),
):
    """Analyze watchlist tickers without executing trades."""
    watchlist = db.query(Watchlist).all()
    tickers = [w.ticker for w in watchlist]

    if not tickers:
        return {"error": "No tickers in watchlist. Add tickers in Settings first."}

    broker = _get_active_broker(db)
    risk_manager = RiskManager(
        RiskLimits(
            trailing_stop_pct=trailing_stop_pct,
            take_profit_pct=take_profit_pct,
        )
    )
    trader = AutoTrader(
        broker=broker,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        risk_manager=risk_manager,
    )

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
                "macd_histogram": analysis.macd_histogram,
                "weekly_trend": analysis.weekly_trend,
                "bollinger_squeeze": analysis.bollinger_squeeze,
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
