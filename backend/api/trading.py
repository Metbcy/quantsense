"""Paper-trading endpoints – orders, positions, portfolio, history."""

import logging

from fastapi import APIRouter, HTTPException

from data.yahoo_provider import YahooFinanceProvider
from models.pydantic_models import OrderRequest
from trading.broker import Order, OrderSide, OrderType
from trading.paper_broker import PaperBroker

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singleton
_broker = PaperBroker()
_provider = YahooFinanceProvider()


def _get_broker() -> PaperBroker:
    """Get the shared paper broker instance."""
    return _broker


@router.post("/order")
async def submit_order(req: OrderRequest):
    """Submit a paper-trading order."""
    try:
        side = OrderSide(req.side.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid side '{req.side}'. Use 'buy' or 'sell'.")

    try:
        order_type = OrderType(req.order_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid order_type '{req.order_type}'. Use 'market', 'limit', or 'stop'.",
        )

    # Fetch current price for market orders
    price = req.price
    if order_type == OrderType.MARKET and price is None:
        try:
            quote = await _provider.get_quote(req.ticker)
            price = quote.price
            if price <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not get a valid price for {req.ticker}",
                )
            await _broker.update_prices({req.ticker: price})
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Price fetch failed for %s", req.ticker)
            raise HTTPException(status_code=500, detail="Failed to fetch current price")

    order = Order(
        ticker=req.ticker.upper(),
        side=side,
        order_type=order_type,
        quantity=req.quantity,
        price=price,
    )

    try:
        result = await _broker.submit_order(order)
    except Exception as exc:
        logger.exception("Order execution failed for %s", req.ticker)
        raise HTTPException(status_code=500, detail="Order execution failed")

    return {
        "order_id": result.order_id,
        "status": result.status.value,
        "filled_price": result.filled_price,
        "filled_quantity": result.filled_quantity,
        "timestamp": result.timestamp.isoformat(),
        "message": result.message,
    }


@router.get("/positions")
async def get_positions():
    """Get all open positions."""
    try:
        positions = await _broker.get_positions()
        return [
            {
                "ticker": p.ticker,
                "quantity": p.quantity,
                "avg_cost": p.avg_cost,
                "current_price": p.current_price,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "market_value": p.market_value,
            }
            for p in positions
        ]
    except Exception as exc:
        logger.exception("Failed to fetch positions")
        raise HTTPException(status_code=500, detail="Failed to fetch positions")


@router.get("/portfolio")
async def get_portfolio():
    """Get portfolio summary."""
    try:
        portfolio = await _broker.get_portfolio()
        return {
            "total_value": portfolio.total_value,
            "cash": portfolio.cash,
            "positions_value": portfolio.positions_value,
            "total_pnl": portfolio.total_pnl,
            "total_pnl_pct": portfolio.total_pnl_pct,
            "daily_pnl": portfolio.daily_pnl,
            "positions": [
                {
                    "ticker": p.ticker,
                    "quantity": p.quantity,
                    "avg_cost": p.avg_cost,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                    "market_value": p.market_value,
                }
                for p in portfolio.positions
            ],
        }
    except Exception as exc:
        logger.exception("Failed to fetch portfolio")
        raise HTTPException(status_code=500, detail="Failed to fetch portfolio")


@router.get("/history")
async def get_trade_history():
    """Get trade history."""
    try:
        trades = await _broker.get_trade_history()
        serialized = []
        for t in trades:
            entry = dict(t)
            if "timestamp" in entry and hasattr(entry["timestamp"], "isoformat"):
                entry["timestamp"] = entry["timestamp"].isoformat()
            serialized.append(entry)
        return serialized
    except Exception as exc:
        logger.exception("Failed to fetch trade history")
        raise HTTPException(status_code=500, detail="Failed to fetch trade history")


@router.post("/reset")
async def reset_broker():
    """Reset paper broker to initial state."""
    _broker.reset()
    return {"detail": "Paper broker reset to initial state"}
