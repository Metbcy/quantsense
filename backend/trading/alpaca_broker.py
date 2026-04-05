import asyncio
import logging
from datetime import datetime
from typing import Optional

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)
from alpaca.trading.enums import OrderSide as AlpacaSide, OrderType as AlpacaType, TimeInForce, QueryOrderStatus
from alpaca.common.exceptions import APIError

from config.settings import settings
from trading.broker import (
    Broker,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSummary,
    PositionInfo,
)

logger = logging.getLogger(__name__)

class AlpacaBroker(Broker):
    """Broker implementation for Alpaca Markets."""

    def __init__(self, api_key: Optional[str] = None, secret_key: Optional[str] = None, paper: bool = True):
        self.api_key = api_key or settings.ALPACA_API_KEY
        self.secret_key = secret_key or settings.ALPACA_SECRET_KEY
        self.paper = paper if paper is not None else settings.ALPACA_PAPER
        
        if not self.api_key or not self.secret_key:
            logger.warning("Alpaca API credentials not fully provided. AlpacaBroker will be non-functional.")
            self.client = None
        else:
            self.client = TradingClient(self.api_key, self.secret_key, paper=self.paper)

    @property
    def is_available(self) -> bool:
        return self.client is not None

    async def submit_order(self, order: Order) -> OrderResult:
        if not self.client:
            raise RuntimeError("Alpaca client not initialized")

        # Map side
        side = AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL
        
        # Map order request
        if order.order_type == OrderType.MARKET:
            req = MarketOrderRequest(
                symbol=order.ticker,
                qty=order.quantity,
                side=side,
                time_in_force=TimeInForce.GTC
            )
        elif order.order_type == OrderType.LIMIT:
            req = LimitOrderRequest(
                symbol=order.ticker,
                qty=order.quantity,
                side=side,
                limit_price=order.price,
                time_in_force=TimeInForce.GTC
            )
        elif order.order_type == OrderType.STOP:
            req = StopOrderRequest(
                symbol=order.ticker,
                qty=order.quantity,
                side=side,
                stop_price=order.stop_price,
                time_in_force=TimeInForce.GTC
            )
        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

        try:
            # SDK is synchronous, wrap in thread
            placed_order = await asyncio.to_thread(lambda: self.client.submit_order(req))
            
            return OrderResult(
                order_id=str(placed_order.id),
                status=self._map_status(placed_order.status),
                filled_price=float(placed_order.filled_avg_price or 0.0),
                filled_quantity=float(placed_order.filled_qty or 0.0),
                timestamp=placed_order.created_at,
                message=f"Alpaca order {placed_order.status}"
            )
        except Exception as e:
            logger.error(f"Alpaca order submission failed: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        if not self.client: return False
        try:
            await asyncio.to_thread(lambda: self.client.cancel_order_by_id(order_id))
            return True
        except Exception:
            return False

    async def get_positions(self) -> list[PositionInfo]:
        if not self.client: return []
        try:
            positions = await asyncio.to_thread(lambda: self.client.get_all_positions())
            return [
                PositionInfo(
                    ticker=p.symbol,
                    quantity=float(p.qty),
                    avg_cost=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl=float(p.unrealized_pl),
                    unrealized_pnl_pct=float(p.unrealized_plpc) * 100,
                    market_value=float(p.market_value)
                )
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca positions: {e}")
            return []

    async def get_portfolio(self) -> PortfolioSummary:
        if not self.client:
            return PortfolioSummary(0, 0, 0, 0, 0)
        
        try:
            account = await asyncio.to_thread(lambda: self.client.get_account())
            positions = await self.get_positions()
            
            total_value = float(account.portfolio_value)
            cash = float(account.cash)
            pos_value = sum(p.market_value for p in positions)
            
            # Simple PnL calc from account equity vs initial (Alpaca doesn't easily give 'initial' this way)
            # We'll use the daily PnL provided by account
            daily_pnl = float(account.equity) - float(account.last_equity)
            
            return PortfolioSummary(
                total_value=total_value,
                cash=cash,
                positions_value=pos_value,
                total_pnl=total_value - float(account.last_equity), # Approximation
                total_pnl_pct=((total_value / float(account.last_equity)) - 1) * 100 if float(account.last_equity) > 0 else 0,
                positions=positions,
                daily_pnl=daily_pnl
            )
        except Exception as e:
            logger.error(f"Failed to fetch Alpaca portfolio: {e}")
            return PortfolioSummary(0, 0, 0, 0, 0)

    async def get_trade_history(self) -> list[dict]:
        if not self.client: return []
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=50)
            orders = await asyncio.to_thread(lambda: self.client.get_orders(req))
            return [
                {
                    "id": str(o.id),
                    "ticker": o.symbol,
                    "side": o.side.value,
                    "order_type": o.order_type.value,
                    "price": float(o.filled_avg_price or 0),
                    "quantity": float(o.filled_qty or 0),
                    "status": o.status.value,
                    "timestamp": o.created_at.isoformat()
                }
                for o in orders
            ]
        except Exception:
            return []

    def _map_status(self, alpaca_status) -> OrderStatus:
        from alpaca.trading.enums import OrderStatus as AS
        if alpaca_status in (AS.FILLED, AS.PARTIALLY_FILLED):
            return OrderStatus.FILLED
        if alpaca_status in (AS.CANCELED, AS.EXPIRED):
            return OrderStatus.CANCELLED
        if alpaca_status in (AS.REJECTED, AS.HELD):
            return OrderStatus.REJECTED
        return OrderStatus.PENDING
