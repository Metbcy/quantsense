from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from models.database import init_db
from api.backtest import router as backtest_router
from api.sentiment import router as sentiment_router
from api.trading import router as trading_router
from api.market import router as market_router
from api.settings import router as settings_router
from api.websocket import router as ws_router
from api.auto_trade import router as auto_trade_router


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3030"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market_router, prefix="/api/market", tags=["market"])
app.include_router(backtest_router, prefix="/api/backtest", tags=["backtest"])
app.include_router(sentiment_router, prefix="/api/sentiment", tags=["sentiment"])
app.include_router(trading_router, prefix="/api/trading", tags=["trading"])
app.include_router(auto_trade_router, prefix="/api/auto-trade", tags=["auto-trade"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(ws_router, prefix="/api/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
