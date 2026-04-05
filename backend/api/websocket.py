"""WebSocket endpoint – live portfolio, price, and sentiment updates."""

import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from data.shared import provider as _shared_provider
from models.database import SessionLocal
from models.schemas import Watchlist
from api.trading import _get_active_broker, _load_broker_from_db

logger = logging.getLogger(__name__)

router = APIRouter()

from config.settings import settings as _settings

ALLOWED_ORIGINS = {o.strip() for o in _settings.CORS_ORIGINS.split(",") if o.strip()}


class ConnectionManager:
    """Manage active WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()
_provider = _shared_provider


def _get_watchlist_tickers() -> list[str]:
    """Fetch watchlist tickers from the database (sync helper)."""
    db = SessionLocal()
    try:
        tickers = [w.ticker for w in db.query(Watchlist).all()]
        return tickers
    finally:
        db.close()


async def _send_portfolio_update(websocket: WebSocket) -> None:
    """Send current portfolio summary over the WebSocket."""
    try:
        db = SessionLocal()
        try:
            broker = _get_active_broker(db)
        finally:
            db.close()
        portfolio = await broker.get_portfolio()
        await websocket.send_json(
            {
                "type": "portfolio",
                "data": {
                    "total_value": portfolio.total_value,
                    "cash": portfolio.cash,
                    "positions_value": portfolio.positions_value,
                    "total_pnl": portfolio.total_pnl,
                    "total_pnl_pct": portfolio.total_pnl_pct,
                    "daily_pnl": portfolio.daily_pnl,
                },
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as exc:
        logger.debug("Portfolio update failed: %s", exc)


async def _send_price_updates(websocket: WebSocket) -> None:
    """Send price updates for watchlist tickers."""
    try:
        tickers = _get_watchlist_tickers()
        for ticker in tickers:
            quote = await _provider.get_quote(ticker)
            await websocket.send_json(
                {
                    "type": "price",
                    "data": {
                        "ticker": quote.ticker,
                        "price": quote.price,
                        "change": quote.change,
                        "change_percent": quote.change_percent,
                        "volume": quote.volume,
                    },
                    "timestamp": datetime.now().isoformat(),
                }
            )
    except Exception as exc:
        logger.debug("Price update failed: %s", exc)


@router.websocket("/live")
async def websocket_live(websocket: WebSocket):
    """Live WebSocket feed for portfolio, price, and sentiment updates."""
    origin = (websocket.headers.get("origin") or "").rstrip("/")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=4003, reason="Origin not allowed")
        return

    await manager.connect(websocket)
    try:
        while True:
            # Send portfolio update
            await _send_portfolio_update(websocket)

            # Send price updates for watchlist tickers
            await _send_price_updates(websocket)

            # Wait before next cycle
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
