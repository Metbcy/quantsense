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
from api.auth import router as auth_router
from api.backtest import router as backtest_router
from api.sentiment import router as sentiment_router
from api.trading import router as trading_router
from api.market import router as market_router
from api.settings import router as settings_router
from api.websocket import router as ws_router
from api.auto_trade import router as auto_trade_router
from api.webhooks import router as webhooks_router
from api.portfolio_history import router as portfolio_history_router

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    logger.info("QuantSense API started")
    if settings.WEBHOOK_SECRET == "quantsense_secret_123":
        logger.warning(
            "WEBHOOK_SECRET is using the default placeholder — "
            "set a secure value via the WEBHOOK_SECRET env var"
        )
    # Start background sentiment scheduler
    from sentiment.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("QuantSense API shutting down")


app = FastAPI(
    title="QuantSense API",
    description="AI-powered quantitative trading platform",
    version="1.0.0",
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
app.include_router(sentiment_router, prefix="/api/sentiment", tags=["sentiment"])
app.include_router(trading_router, prefix="/api/trading", tags=["trading"])
app.include_router(auto_trade_router, prefix="/api/auto-trade", tags=["auto-trade"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(ws_router, prefix="/api/ws", tags=["websocket"])
app.include_router(portfolio_history_router, prefix="/api/portfolio", tags=["portfolio"])


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
        content={"status": status, "version": "1.0.0", "database": "ok" if db_ok else "unreachable"},
    )
