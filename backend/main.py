import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config.settings import settings
from models.database import init_db
from api.backtest import router as backtest_router
from api.sentiment import router as sentiment_router
from api.trading import router as trading_router
from api.market import router as market_router
from api.settings import router as settings_router
from api.websocket import router as ws_router
from api.auto_trade import router as auto_trade_router
from api.webhooks import router as webhooks_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


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


# --- Global error handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
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
app.include_router(market_router, prefix="/api/market", tags=["market"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(sentiment_router, prefix="/api/sentiment", tags=["sentiment"])
app.include_router(trading_router, prefix="/api/trading", tags=["trading"])
app.include_router(auto_trade_router, prefix="/api/auto-trade", tags=["auto-trade"])
app.include_router(webhooks_router, prefix="/api/webhooks", tags=["webhooks"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(ws_router, prefix="/api/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
