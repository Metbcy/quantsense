from datetime import datetime

from .broker import (
    Broker,
    Order,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSummary,
    PositionInfo,
)


class PaperBroker(Broker):
    def __init__(self, initial_cash: float = 100000.0):
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.positions: dict[str, dict] = {}  # ticker -> {quantity, avg_cost}
        self.trades: list[dict] = []
        self.pending_orders: list[dict] = []
        self._order_counter = 0
        self._current_prices: dict[str, float] = {}
        self._portfolio_history: list[tuple[datetime, float]] = []
        self._daily_starting_value: float | None = None

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"PAPER-{self._order_counter:06d}"

    def _get_price(self, ticker: str, order: Order) -> float | None:
        """Resolve the effective market price for a ticker."""
        if ticker in self._current_prices:
            return self._current_prices[ticker]
        if order.price is not None:
            return order.price
        return None

    def _record_trade(
        self,
        order_id: str,
        order: Order,
        filled_price: float,
        realized_pnl: float = 0.0,
    ) -> None:
        self.trades.append(
            {
                "order_id": order_id,
                "ticker": order.ticker,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": order.quantity,
                "price": filled_price,
                "realized_pnl": realized_pnl,
                "timestamp": datetime.now(),
            }
        )

    def _snapshot_portfolio_value(self) -> None:
        positions_value = sum(
            pos["quantity"] * self._current_prices.get(ticker, pos["avg_cost"])
            for ticker, pos in self.positions.items()
        )
        total = self.cash + positions_value
        self._portfolio_history.append((datetime.now(), total))

    def _fill_buy(self, order: Order, fill_price: float) -> OrderResult:
        order_id = self._next_order_id()
        cost = fill_price * order.quantity

        if cost > self.cash:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_price=0.0,
                filled_quantity=0.0,
                timestamp=datetime.now(),
                message=f"Insufficient cash: need ${cost:.2f}, have ${self.cash:.2f}",
            )

        self.cash -= cost
        if order.ticker in self.positions:
            pos = self.positions[order.ticker]
            total_qty = pos["quantity"] + order.quantity
            pos["avg_cost"] = (
                (pos["avg_cost"] * pos["quantity"]) + (fill_price * order.quantity)
            ) / total_qty
            pos["quantity"] = total_qty
        else:
            self.positions[order.ticker] = {
                "quantity": order.quantity,
                "avg_cost": fill_price,
            }

        self._current_prices[order.ticker] = fill_price
        self._record_trade(order_id, order, fill_price)
        self._snapshot_portfolio_value()

        return OrderResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_price=fill_price,
            filled_quantity=order.quantity,
            timestamp=datetime.now(),
            message=f"Bought {order.quantity} {order.ticker} @ ${fill_price:.2f}",
        )

    def _fill_sell(self, order: Order, fill_price: float) -> OrderResult:
        order_id = self._next_order_id()

        if order.ticker not in self.positions:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_price=0.0,
                filled_quantity=0.0,
                timestamp=datetime.now(),
                message=f"No position in {order.ticker}",
            )

        pos = self.positions[order.ticker]
        if pos["quantity"] < order.quantity:
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.REJECTED,
                filled_price=0.0,
                filled_quantity=0.0,
                timestamp=datetime.now(),
                message=(
                    f"Insufficient shares: have {pos['quantity']}, "
                    f"need {order.quantity}"
                ),
            )

        realized_pnl = (fill_price - pos["avg_cost"]) * order.quantity
        proceeds = fill_price * order.quantity
        self.cash += proceeds

        pos["quantity"] -= order.quantity
        if pos["quantity"] <= 1e-9:
            del self.positions[order.ticker]

        self._current_prices[order.ticker] = fill_price
        self._record_trade(order_id, order, fill_price, realized_pnl)
        self._snapshot_portfolio_value()

        return OrderResult(
            order_id=order_id,
            status=OrderStatus.FILLED,
            filled_price=fill_price,
            filled_quantity=order.quantity,
            timestamp=datetime.now(),
            message=(
                f"Sold {order.quantity} {order.ticker} @ ${fill_price:.2f} "
                f"(PnL: ${realized_pnl:+.2f})"
            ),
        )

    async def submit_order(self, order: Order) -> OrderResult:
        market_price = self._get_price(order.ticker, order)

        if order.order_type == OrderType.MARKET:
            if market_price is None:
                return OrderResult(
                    order_id=self._next_order_id(),
                    status=OrderStatus.REJECTED,
                    filled_price=0.0,
                    filled_quantity=0.0,
                    timestamp=datetime.now(),
                    message=(
                        f"No price available for {order.ticker}. "
                        "Set order.price or call update_prices first."
                    ),
                )
            if order.side == OrderSide.BUY:
                return self._fill_buy(order, market_price)
            return self._fill_sell(order, market_price)

        if order.order_type == OrderType.LIMIT:
            if order.price is None:
                return OrderResult(
                    order_id=self._next_order_id(),
                    status=OrderStatus.REJECTED,
                    filled_price=0.0,
                    filled_quantity=0.0,
                    timestamp=datetime.now(),
                    message="Limit orders require a price",
                )
            can_fill = False
            if market_price is not None:
                if order.side == OrderSide.BUY and market_price <= order.price:
                    can_fill = True
                elif order.side == OrderSide.SELL and market_price >= order.price:
                    can_fill = True

            if can_fill and market_price is not None:
                if order.side == OrderSide.BUY:
                    return self._fill_buy(order, market_price)
                return self._fill_sell(order, market_price)

            # Keep as pending
            order_id = self._next_order_id()
            self.pending_orders.append(
                {"order_id": order_id, "order": order, "created_at": datetime.now()}
            )
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.PENDING,
                filled_price=0.0,
                filled_quantity=0.0,
                timestamp=datetime.now(),
                message=f"Limit order pending: {order.side.value} {order.quantity} {order.ticker} @ ${order.price:.2f}",
            )

        if order.order_type == OrderType.STOP:
            if order.stop_price is None:
                return OrderResult(
                    order_id=self._next_order_id(),
                    status=OrderStatus.REJECTED,
                    filled_price=0.0,
                    filled_quantity=0.0,
                    timestamp=datetime.now(),
                    message="Stop orders require a stop_price",
                )
            triggered = False
            if market_price is not None:
                if order.side == OrderSide.SELL and market_price <= order.stop_price:
                    triggered = True
                elif order.side == OrderSide.BUY and market_price >= order.stop_price:
                    triggered = True

            if triggered and market_price is not None:
                if order.side == OrderSide.BUY:
                    return self._fill_buy(order, market_price)
                return self._fill_sell(order, market_price)

            order_id = self._next_order_id()
            self.pending_orders.append(
                {"order_id": order_id, "order": order, "created_at": datetime.now()}
            )
            return OrderResult(
                order_id=order_id,
                status=OrderStatus.PENDING,
                filled_price=0.0,
                filled_quantity=0.0,
                timestamp=datetime.now(),
                message=(
                    f"Stop order pending: {order.side.value} {order.quantity} "
                    f"{order.ticker} @ stop ${order.stop_price:.2f}"
                ),
            )

        return OrderResult(
            order_id=self._next_order_id(),
            status=OrderStatus.REJECTED,
            filled_price=0.0,
            filled_quantity=0.0,
            timestamp=datetime.now(),
            message=f"Unsupported order type: {order.order_type}",
        )

    async def cancel_order(self, order_id: str) -> bool:
        for i, pending in enumerate(self.pending_orders):
            if pending["order_id"] == order_id:
                self.pending_orders.pop(i)
                return True
        return False

    async def get_positions(self) -> list[PositionInfo]:
        result: list[PositionInfo] = []
        for ticker, pos in self.positions.items():
            current_price = self._current_prices.get(ticker, pos["avg_cost"])
            quantity = pos["quantity"]
            avg_cost = pos["avg_cost"]
            market_value = current_price * quantity
            cost_basis = avg_cost * quantity
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (
                (unrealized_pnl / cost_basis) * 100 if cost_basis else 0.0
            )
            result.append(
                PositionInfo(
                    ticker=ticker,
                    quantity=quantity,
                    avg_cost=avg_cost,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=unrealized_pnl_pct,
                    market_value=market_value,
                )
            )
        return result

    async def get_portfolio(self) -> PortfolioSummary:
        positions = await self.get_positions()
        positions_value = sum(p.market_value for p in positions)
        total_value = self.cash + positions_value
        total_pnl = total_value - self.initial_cash
        total_pnl_pct = (
            (total_pnl / self.initial_cash) * 100 if self.initial_cash else 0.0
        )

        daily_pnl = 0.0
        if self._daily_starting_value is not None:
            daily_pnl = total_value - self._daily_starting_value
        else:
            self._daily_starting_value = total_value

        return PortfolioSummary(
            total_value=total_value,
            cash=self.cash,
            positions_value=positions_value,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            positions=positions,
            daily_pnl=daily_pnl,
        )

    async def get_trade_history(self) -> list[dict]:
        return list(self.trades)

    async def update_prices(self, prices: dict[str, float]) -> None:
        """Update current market prices and process pending orders."""
        self._current_prices.update(prices)
        self._snapshot_portfolio_value()

        filled: list[int] = []
        for i, pending in enumerate(self.pending_orders):
            order: Order = pending["order"]
            if order.ticker not in prices:
                continue
            market_price = prices[order.ticker]

            if order.order_type == OrderType.LIMIT:
                can_fill = False
                if order.side == OrderSide.BUY and market_price <= order.price:  # type: ignore[operator]
                    can_fill = True
                elif order.side == OrderSide.SELL and market_price >= order.price:  # type: ignore[operator]
                    can_fill = True
                if can_fill:
                    if order.side == OrderSide.BUY:
                        self._fill_buy(order, market_price)
                    else:
                        self._fill_sell(order, market_price)
                    filled.append(i)

            elif order.order_type == OrderType.STOP:
                triggered = False
                if (
                    order.side == OrderSide.SELL
                    and market_price <= order.stop_price  # type: ignore[operator]
                ):
                    triggered = True
                elif (
                    order.side == OrderSide.BUY
                    and market_price >= order.stop_price  # type: ignore[operator]
                ):
                    triggered = True
                if triggered:
                    if order.side == OrderSide.BUY:
                        self._fill_buy(order, market_price)
                    else:
                        self._fill_sell(order, market_price)
                    filled.append(i)

        for idx in reversed(filled):
            self.pending_orders.pop(idx)

    def get_portfolio_value_history(self) -> list[tuple[datetime, float]]:
        """Return portfolio value snapshots over time."""
        return list(self._portfolio_history)

    def reset(self, initial_cash: float = 100000.0) -> None:
        """Reset the paper broker to initial state."""
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.positions.clear()
        self.trades.clear()
        self.pending_orders.clear()
        self._order_counter = 0
        self._current_prices.clear()
        self._portfolio_history.clear()
        self._daily_starting_value = None
