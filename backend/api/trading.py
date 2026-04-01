"""Paper-trading endpoints – orders, positions, portfolio, history.

All state is persisted to the database so it survives server restarts.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from data.yahoo_provider import YahooFinanceProvider
from models.database import get_db
from models.pydantic_models import OrderRequest
from models.schemas import Portfolio as PortfolioDB, Position as PositionDB, Trade as TradeDB
from trading.broker import Order, OrderSide, OrderType
from trading.paper_broker import PaperBroker

logger = logging.getLogger(__name__)

router = APIRouter()

_provider = YahooFinanceProvider()
_broker: PaperBroker | None = None
_broker_loaded = False


def _get_or_create_portfolio(db: Session) -> PortfolioDB:
    """Get the default portfolio from DB, creating if needed."""
    portfolio = db.query(PortfolioDB).filter(PortfolioDB.name == "default").first()
    if not portfolio:
        portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def _load_broker_from_db(db: Session) -> PaperBroker:
    """Load broker state from database."""
    global _broker, _broker_loaded
    if _broker_loaded and _broker is not None:
        return _broker

    portfolio = _get_or_create_portfolio(db)
    _broker = PaperBroker(initial_cash=portfolio.initial_cash)
    _broker.cash = portfolio.cash

    # Load positions
    positions = db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).all()
    for pos in positions:
        if pos.quantity > 0:
            _broker.positions[pos.ticker] = {
                "quantity": pos.quantity,
                "avg_cost": pos.avg_cost,
            }

    # Load trade history
    trades = (
        db.query(TradeDB)
        .filter(TradeDB.portfolio_id == portfolio.id)
        .order_by(TradeDB.created_at.asc())
        .all()
    )
    for t in trades:
        _broker.trades.append({
            "order_id": str(t.id),
            "ticker": t.ticker,
            "side": t.side,
            "order_type": t.order_type or "market",
            "price": t.price,
            "quantity": t.quantity,
            "value": t.value or (t.price * t.quantity),
            "timestamp": t.created_at,
        })

    _broker_loaded = True
    logger.info(
        "Loaded portfolio: cash=$%.2f, %d positions, %d trades",
        _broker.cash,
        len(_broker.positions),
        len(_broker.trades),
    )
    return _broker


def _save_broker_to_db(db: Session):
    """Persist current broker state to database."""
    if _broker is None:
        return

    portfolio = _get_or_create_portfolio(db)
    portfolio.cash = _broker.cash

    # Sync positions
    db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).delete()
    for ticker, pos_data in _broker.positions.items():
        db_pos = PositionDB(
            portfolio_id=portfolio.id,
            ticker=ticker,
            quantity=pos_data["quantity"],
            avg_cost=pos_data["avg_cost"],
            current_price=pos_data.get("last_price", pos_data["avg_cost"]),
            unrealized_pnl=0,
        )
        db.add(db_pos)

    db.commit()


def _save_trade_to_db(db: Session, order: Order, result, price: float):
    """Save a single executed trade to the database."""
    portfolio = _get_or_create_portfolio(db)
    trade = TradeDB(
        portfolio_id=portfolio.id,
        ticker=order.ticker,
        side=order.side.value,
        order_type=order.order_type.value,
        price=price,
        quantity=result.filled_quantity,
        value=price * result.filled_quantity,
        strategy_name=None,
        sentiment_score=None,
        status=result.status.value,
    )
    db.add(trade)
    portfolio.cash = _broker.cash
    db.commit()


def _get_broker(db: Session | None = None) -> PaperBroker:
    """Get the shared paper broker instance (loading from DB on first call)."""
    global _broker, _broker_loaded
    if _broker_loaded and _broker is not None:
        return _broker
    if db is not None:
        return _load_broker_from_db(db)
    # Fallback: create empty broker (should not normally happen)
    _broker = PaperBroker()
    _broker_loaded = True
    return _broker


@router.post("/order")
async def submit_order(req: OrderRequest, db: Session = Depends(get_db)):
    """Submit a paper-trading order."""
    broker = _load_broker_from_db(db)

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
            await broker.update_prices({req.ticker: price})
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
        result = await broker.submit_order(order)
    except Exception as exc:
        logger.exception("Order execution failed for %s", req.ticker)
        raise HTTPException(status_code=500, detail="Order execution failed")

    # Persist to DB
    _save_trade_to_db(db, order, result, price or 0)
    _save_broker_to_db(db)

    return {
        "order_id": result.order_id,
        "status": result.status.value,
        "filled_price": result.filled_price,
        "filled_quantity": result.filled_quantity,
        "timestamp": result.timestamp.isoformat(),
        "message": result.message,
    }


@router.get("/positions")
async def get_positions(db: Session = Depends(get_db)):
    """Get all open positions."""
    broker = _load_broker_from_db(db)
    try:
        positions = await broker.get_positions()
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
async def get_portfolio(db: Session = Depends(get_db)):
    """Get portfolio summary."""
    broker = _load_broker_from_db(db)
    try:
        portfolio = await broker.get_portfolio()
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
async def get_trade_history(db: Session = Depends(get_db)):
    """Get trade history from database."""
    portfolio = _get_or_create_portfolio(db)
    trades = (
        db.query(TradeDB)
        .filter(TradeDB.portfolio_id == portfolio.id)
        .order_by(TradeDB.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "ticker": t.ticker,
            "side": t.side,
            "order_type": t.order_type or "market",
            "price": t.price,
            "quantity": t.quantity,
            "value": t.value or (t.price * t.quantity),
            "status": t.status,
            "timestamp": t.created_at.isoformat() if t.created_at else None,
        }
        for t in trades
    ]


@router.post("/reset")
async def reset_broker(db: Session = Depends(get_db)):
    """Reset paper broker to initial state and clear DB."""
    global _broker, _broker_loaded

    portfolio = _get_or_create_portfolio(db)

    # Clear DB records
    db.query(TradeDB).filter(TradeDB.portfolio_id == portfolio.id).delete()
    db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).delete()
    portfolio.cash = portfolio.initial_cash
    db.commit()

    # Reset in-memory broker
    _broker = PaperBroker(initial_cash=portfolio.initial_cash)
    _broker_loaded = True

    return {"detail": "Paper broker reset to initial state"}
