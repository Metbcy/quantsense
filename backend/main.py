import asyncio
import logging
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config.settings import settings
from models.database import init_db, SessionLocal
from models.schemas import (
    Portfolio as PortfolioDB,
    PortfolioSnapshot,
    Position as PositionDB,
)
from api.auth import router as auth_router
from api.backtest import router as backtest_router
from api.backtest_factors import router as backtest_factors_router
from api.backtest_portfolio import router as backtest_portfolio_router
from api.sentiment import router as sentiment_router
from api.trading import router as trading_router
from api.market import router as market_router
from api.settings import router as settings_router
from api.websocket import router as ws_router
from api.portfolio_history import router as portfolio_history_router

# NOTE: the OHLCV data layer caches in two stages:
#   1. ``data.shared.parquet_cache`` — a process-wide ParquetOHLCVCache that
#      durably stores one Parquet file per ticker under
#      ``settings.QUANTSENSE_CACHE_DIR``. Built at import time from settings,
#      so every request handler sharing ``data.shared.provider`` benefits
#      transparently. Disable with ``QUANTSENSE_CACHE_ENABLED=false``.
#   2. ``data.cache.CachedDataProvider`` — a thin in-process TTL wrapper for
#      hot-path deduplication within a single API session.
# The wiring lives in ``data/shared.py`` so the ``provider`` singleton is
# constructed once, before any router imports it.

logger = logging.getLogger(__name__)

# --- Structured logging setup ---
LOG_FORMAT = "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"


class RequestIdFilter(logging.Filter):
    """Inject request_id into all log records."""

    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def _snapshot_loop():
    """Take a portfolio snapshot every hour."""
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            db = SessionLocal()
            try:
                portfolio = (
                    db.query(PortfolioDB).filter(PortfolioDB.name == "default").first()
                )
                if portfolio:
                    positions = (
                        db.query(PositionDB)
                        .filter(PositionDB.portfolio_id == portfolio.id)
                        .all()
                    )
                    positions_value = sum(
                        p.current_price * p.quantity
                        for p in positions
                        if p.quantity > 0
                    )
                    total_value = portfolio.cash + positions_value
                    snap = PortfolioSnapshot(
                        portfolio_id=portfolio.id,
                        total_value=total_value,
                        cash=portfolio.cash,
                        positions_value=positions_value,
                    )
                    db.add(snap)
                    db.commit()
                    logger.info("Portfolio snapshot: $%.2f", total_value)
            finally:
                db.close()
        except Exception:
            logger.exception("Snapshot task failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    logger.info("QuantSense API started")
    # Start background sentiment scheduler
    from sentiment.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    snapshot_task = asyncio.create_task(_snapshot_loop())
    yield
    snapshot_task.cancel()
    stop_scheduler()
    logger.info("QuantSense API shutting down")


app = FastAPI(
    title="QuantSense API",
    description="A research-grade equity backtesting and signal platform",
    version="2.0.0",
    lifespan=lifespan,
)

# --- CORS (configurable via CORS_ORIGINS env var) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request ID + logging middleware ---
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    request.state.request_id = request_id

    # Thread request_id into all loggers for this request
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.request_id = request_id
        return record

    logging.setLogRecordFactory(record_factory)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        logging.setLogRecordFactory(old_factory)
    elapsed_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# --- Global error handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "-")
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": type(exc).__name__,
            "request_id": request_id,
        },
    )


# --- Rate limiting middleware ---
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
except ImportError:
    # slowapi not installed — rate limiting disabled
    pass


# --- Routes ---
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(market_router, prefix="/api/market", tags=["market"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(backtest_portfolio_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(backtest_factors_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(sentiment_router, prefix="/api/sentiment", tags=["sentiment"])
app.include_router(trading_router, prefix="/api/trading", tags=["trading"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(ws_router, prefix="/api/ws", tags=["websocket"])
app.include_router(
    portfolio_history_router, prefix="/api/portfolio", tags=["portfolio"]
)


@app.get("/api/health")
async def health():
    """Health check that verifies database connectivity."""
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)

    status = "ok" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "version": "1.0.0",
            "database": "ok" if db_ok else "unreachable",
        },
    )
