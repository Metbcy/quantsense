"""Background auto-trade scheduler using APScheduler.

Runs periodic autonomous trading cycles during US market hours.
Follows the same APScheduler pattern as sentiment/scheduler.py.
"""

import logging
from collections import deque
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from models.database import SessionLocal
from models.schemas import Watchlist
from trading.auto_trader import AutoTrader
from trading.risk_manager import RiskManager, RiskLimits

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_interval_minutes: int = 30
_total_cycles: int = 0
_last_run: datetime | None = None
_cycle_history: deque[dict] = deque(maxlen=20)

_EASTERN = pytz.timezone("US/Eastern")


def _is_market_hours() -> bool:
    """Check if current time is within US market hours (weekdays 9:30-16:00 ET)."""
    now_et = datetime.now(_EASTERN)
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


async def _run_auto_trade_cycle(broker_factory, db_session_factory) -> None:
    """Execute one auto-trade cycle: fetch watchlist, run AutoTrader."""
    global _total_cycles, _last_run

    if not _is_market_hours():
        logger.debug("Auto-trade scheduler: outside market hours, skipping")
        return

    db = db_session_factory()
    try:
        tickers = [w.ticker for w in db.query(Watchlist).all()]
        if not tickers:
            logger.debug("Auto-trade scheduler: watchlist empty, skipping")
            return

        logger.info("Auto-trade scheduler: running cycle for %d tickers", len(tickers))
        broker = broker_factory(db)
        trader = AutoTrader(broker=broker)

        result = await trader.run_cycle(tickers)

        # Persist trades
        from api.trading import _save_broker_to_db
        _save_broker_to_db(db)

        _total_cycles += 1
        _last_run = datetime.now()

        cycle_record = {
            "cycle": _total_cycles,
            "timestamp": _last_run.isoformat(),
            "tickers_count": len(tickers),
            "decisions": len(result.get("decisions", [])),
            "executions": len(result.get("executions", [])),
            "portfolio_value": result.get("portfolio", {}).get("total_value"),
            "status": "success",
        }
        _cycle_history.append(cycle_record)

        logger.info(
            "Auto-trade cycle #%d complete: %d decisions, %d executions",
            _total_cycles,
            len(result.get("decisions", [])),
            len(result.get("executions", [])),
        )
    except Exception:
        _total_cycles += 1
        _last_run = datetime.now()
        _cycle_history.append({
            "cycle": _total_cycles,
            "timestamp": _last_run.isoformat(),
            "status": "error",
        })
        logger.exception("Auto-trade cycle #%d failed", _total_cycles)
    finally:
        db.close()


def start_scheduler(
    interval_minutes: int = 30,
    broker_factory=None,
    db_session_factory=None,
) -> AsyncIOScheduler:
    """Start the background auto-trade scheduler."""
    global _scheduler, _interval_minutes

    if _scheduler is not None and _scheduler.running:
        logger.warning("Auto-trade scheduler already running")
        return _scheduler

    if db_session_factory is None:
        db_session_factory = SessionLocal
    if broker_factory is None:
        from api.trading import _get_active_broker
        broker_factory = _get_active_broker

    _interval_minutes = interval_minutes
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_auto_trade_cycle,
        IntervalTrigger(minutes=interval_minutes),
        args=[broker_factory, db_session_factory],
        id="auto_trade_cycle",
        name=f"Auto-trade cycle (every {interval_minutes}m)",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Auto-trade scheduler started (interval=%dm)", interval_minutes)
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the auto-trade scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Auto-trade scheduler stopped")


def get_scheduler_status() -> dict:
    """Return current scheduler status."""
    running = _scheduler is not None and _scheduler.running
    next_run: str | None = None

    if running and _scheduler is not None:
        job = _scheduler.get_job("auto_trade_cycle")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return {
        "running": running,
        "interval_minutes": _interval_minutes,
        "next_run": next_run,
        "last_run": _last_run.isoformat() if _last_run else None,
        "total_cycles": _total_cycles,
        "cycle_history": list(_cycle_history),
    }
