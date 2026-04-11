"""Paper-trading endpoints – orders, positions, portfolio, history.

All state is persisted to the database so it survives server restarts.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from data.shared import provider as _provider_instance
from models.database import get_db
from models.pydantic_models import OrderRequest
from models.schemas import Portfolio as PortfolioDB, Position as PositionDB, PortfolioSnapshot, Trade as TradeDB, User
from trading.broker import Broker, Order, OrderSide, OrderStatus, OrderType
from trading.paper_broker import PaperBroker
from trading.alpaca_broker import AlpacaBroker
from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_provider = _provider_instance
_paper_broker: PaperBroker | None = None
_alpaca_broker: AlpacaBroker | None = None
_paper_broker_loaded = False


def _get_active_broker(db: Session) -> Broker:
    """Returns AlpacaBroker if configured, otherwise PaperBroker."""
    global _alpaca_broker, _paper_broker, _paper_broker_loaded
    
    if settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY:
        if _alpaca_broker is None:
            _alpaca_broker = AlpacaBroker()
        if _alpaca_broker.is_available:
            return _alpaca_broker

    if not _paper_broker_loaded:
        _paper_broker = _load_broker_from_db(db)
        _paper_broker_loaded = True
    
    return _paper_broker


def _get_or_create_portfolio(db: Session, user: User | None = None) -> PortfolioDB:
    """Get the default portfolio from DB, creating if needed."""
    q = db.query(PortfolioDB).filter(PortfolioDB.name == "default")
    if user is not None:
        q = q.filter(PortfolioDB.user_id == user.id)
    else:
        q = q.filter(PortfolioDB.user_id.is_(None))
    portfolio = q.first()
    if not portfolio:
        portfolio = PortfolioDB(
            name="default", cash=100000.0, initial_cash=100000.0,
            user_id=user.id if user else None,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def _load_broker_from_db(db: Session) -> PaperBroker:
    """Load broker state from database."""
    global _paper_broker, _paper_broker_loaded
    if _paper_broker_loaded and _paper_broker is not None:
        return _paper_broker

    portfolio = _get_or_create_portfolio(db)
    _paper_broker = PaperBroker(initial_cash=portfolio.initial_cash)
    _paper_broker.cash = portfolio.cash

    # Load positions and restore current prices
    positions = db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).all()
    for pos in positions:
        if pos.quantity > 0:
            _paper_broker.positions[pos.ticker] = {
                "quantity": pos.quantity,
                "avg_cost": pos.avg_cost,
            }
            if pos.current_price and pos.current_price > 0:
                _paper_broker._current_prices[pos.ticker] = pos.current_price

    # Load trade history
    trades = (
        db.query(TradeDB)
        .filter(TradeDB.portfolio_id == portfolio.id)
        .order_by(TradeDB.created_at.asc())
        .all()
    )
    for t in trades:
        _paper_broker.trades.append({
            "order_id": str(t.id),
            "ticker": t.ticker,
            "side": t.side,
            "order_type": t.order_type or "market",
            "price": t.price,
            "quantity": t.quantity,
            "value": t.value or (t.price * t.quantity),
            "timestamp": t.created_at,
        })

    _paper_broker_loaded = True
    logger.info(
        "Loaded portfolio: cash=$%.2f, %d positions, %d trades",
        _paper_broker.cash,
        len(_paper_broker.positions),
        len(_paper_broker.trades),
    )
    return _paper_broker


def _save_broker_to_db(db: Session):
    """Persist current broker state to database."""
    if _paper_broker is None:
        return

    portfolio = _get_or_create_portfolio(db)
    portfolio.cash = _paper_broker.cash

    # Sync positions
    db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).delete()
    for ticker, pos_data in _paper_broker.positions.items():
        current_price = _paper_broker._current_prices.get(ticker, pos_data["avg_cost"])
        quantity = pos_data["quantity"]
        avg_cost = pos_data["avg_cost"]
        unrealized_pnl = (current_price - avg_cost) * quantity
        db_pos = PositionDB(
            portfolio_id=portfolio.id,
            ticker=ticker,
            quantity=quantity,
            avg_cost=avg_cost,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
        )
        db.add(db_pos)

    db.commit()


def _save_trade_to_db(db: Session, order: Order, result, price: float):
    """Save a single executed trade to the database."""
    if _paper_broker is None:
        return
        
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
    # Get realized_pnl from the paper broker's last recorded trade
    if _paper_broker and _paper_broker.trades:
        last_trade = _paper_broker.trades[-1]
        trade.realized_pnl = last_trade.get("realized_pnl", 0.0)

    db.add(trade)
    portfolio.cash = _paper_broker.cash
    db.commit()


@router.post("/order")
async def submit_order(
    req: OrderRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Submit a paper-trading or live order."""
    broker = _get_active_broker(db)

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
            
            # If paper broker, we manually update its prices to ensure fills
            if isinstance(broker, PaperBroker):
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

    # Persist only if it's the paper broker and the order was filled
    if isinstance(broker, PaperBroker):
        if result.status == OrderStatus.FILLED:
            _save_trade_to_db(db, order, result, result.filled_price)
        _save_broker_to_db(db)

        # Take a snapshot after each trade
        portfolio_db = _get_or_create_portfolio(db, user)
        positions = db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio_db.id).all()
        positions_value = sum(p.current_price * p.quantity for p in positions if p.quantity > 0)
        total_value = portfolio_db.cash + positions_value
        snap = PortfolioSnapshot(
            portfolio_id=portfolio_db.id,
            total_value=total_value,
            cash=portfolio_db.cash,
            positions_value=positions_value,
        )
        db.add(snap)
        db.commit()

    return {
        "order_id": result.order_id,
        "status": result.status.value,
        "filled_price": result.filled_price,
        "filled_quantity": result.filled_quantity,
        "timestamp": result.timestamp.isoformat(),
        "message": result.message,
    }


@router.get("/positions")
async def get_positions(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Get all open positions."""
    broker = _get_active_broker(db)
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
async def get_portfolio(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Get portfolio summary."""
    broker = _get_active_broker(db)
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
async def get_trade_history(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Get trade history (paginated)."""
    broker = _get_active_broker(db)

    if isinstance(broker, AlpacaBroker):
        return await broker.get_trade_history()

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    offset = (page - 1) * page_size

    portfolio = _get_or_create_portfolio(db, user)
    query = (
        db.query(TradeDB)
        .filter(TradeDB.portfolio_id == portfolio.id)
        .order_by(TradeDB.created_at.desc())
    )
    total = query.count()
    trades = query.offset(offset).limit(page_size).all()

    return {
        "items": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "side": t.side,
                "order_type": t.order_type or "market",
                "price": t.price,
                "quantity": t.quantity,
                "value": t.value or (t.price * t.quantity),
                "realized_pnl": getattr(t, 'realized_pnl', 0.0),
                "status": t.status,
                "timestamp": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trades
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/reset")
async def reset_broker(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Reset paper broker to initial state and clear DB. No-op for live brokers."""
    global _paper_broker, _paper_broker_loaded
    broker = _get_active_broker(db)
    
    if isinstance(broker, AlpacaBroker):
        raise HTTPException(status_code=400, detail="Cannot reset a live Alpaca broker via this endpoint.")

    portfolio = _get_or_create_portfolio(db, user)

    # Clear DB records
    db.query(TradeDB).filter(TradeDB.portfolio_id == portfolio.id).delete()
    db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).delete()
    portfolio.cash = portfolio.initial_cash
    db.commit()

    # Reset in-memory broker
    _paper_broker = PaperBroker(initial_cash=portfolio.initial_cash)
    _paper_broker_loaded = True

    return {"detail": "Paper broker reset to initial state"}
