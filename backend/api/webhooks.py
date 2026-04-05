import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config.settings import settings
from models.database import get_db
from models.pydantic_models import TradingViewWebhook
from trading.broker import Order, OrderSide, OrderType
from api.trading import _get_active_broker

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/tradingview")
async def tradingview_webhook(payload: TradingViewWebhook, db: Session = Depends(get_db)):
    """
    Handle alerts from TradingView to execute trades.
    Payload: {"secret": "...", "ticker": "AAPL", "action": "buy", "quantity": 10}
    """
    # 1. Validate secret
    if payload.secret != settings.WEBHOOK_SECRET:
        logger.warning(f"Unauthorized webhook attempt for {payload.ticker}")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # 2. Get active broker
    broker = _get_active_broker(db)
    
    # 3. Create order
    try:
        side = OrderSide(payload.action.lower())
        order_type = OrderType(payload.order_type.lower())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    order = Order(
        ticker=payload.ticker.upper(),
        side=side,
        order_type=order_type,
        quantity=payload.quantity,
        price=payload.price
    )

    # 4. Submit order
    try:
        result = await broker.submit_order(order)
        logger.info(f"Webhook trade executed: {payload.action} {payload.ticker} x{payload.quantity}")
        return {
            "status": "success",
            "order_id": result.order_id,
            "message": result.message
        }
    except Exception as e:
        logger.error(f"Webhook trade failed: {e}")
        raise HTTPException(status_code=500, detail=f"Trade execution failed: {str(e)}")
