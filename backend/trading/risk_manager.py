from dataclasses import dataclass, field
from math import floor

from .broker import Order, OrderSide, OrderType, PortfolioSummary, PositionInfo


@dataclass
class RiskLimits:
    max_position_pct: float = 0.25
    max_daily_loss_pct: float = 0.05
    trailing_stop_pct: float | None = None
    take_profit_pct: float | None = None
    max_open_positions: int = 10


class RiskManager:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self.daily_starting_value: float | None = None
        self._trailing_stops: dict[str, float] = {}  # ticker -> highest price seen
        self._high_water_marks: dict[str, float] = {}

    def check_order(
        self, order: Order, portfolio: PortfolioSummary
    ) -> tuple[bool, str]:
        """Check if order passes risk checks. Returns (allowed, reason)."""
        if self.check_daily_loss_limit(portfolio):
            return False, (
                f"Daily loss limit reached "
                f"({self.limits.max_daily_loss_pct * 100:.1f}% max drawdown)"
            )

        if order.side == OrderSide.BUY:
            price = order.price if order.price is not None else 0.0
            order_value = price * order.quantity

            if order_value > portfolio.cash:
                return False, (
                    f"Insufficient cash: order=${order_value:.2f}, "
                    f"available=${portfolio.cash:.2f}"
                )

            # Check position concentration
            if portfolio.total_value > 0:
                existing_value = 0.0
                for pos in portfolio.positions:
                    if pos.ticker == order.ticker:
                        existing_value = pos.market_value
                        break
                new_position_value = existing_value + order_value
                position_pct = new_position_value / portfolio.total_value
                if position_pct > self.limits.max_position_pct:
                    return False, (
                        f"Position too large: {order.ticker} would be "
                        f"{position_pct * 100:.1f}% of portfolio "
                        f"(max {self.limits.max_position_pct * 100:.1f}%)"
                    )

            # Check max open positions
            current_tickers = {p.ticker for p in portfolio.positions}
            if (
                order.ticker not in current_tickers
                and len(current_tickers) >= self.limits.max_open_positions
            ):
                return False, (
                    f"Max open positions reached ({self.limits.max_open_positions})"
                )

        if order.side == OrderSide.SELL:
            has_position = False
            for pos in portfolio.positions:
                if pos.ticker == order.ticker:
                    has_position = True
                    if order.quantity > pos.quantity:
                        return False, (
                            f"Cannot sell {order.quantity} shares of {order.ticker}: "
                            f"only hold {pos.quantity}"
                        )
                    break
            if not has_position:
                return False, f"No position in {order.ticker} to sell"

        if order.quantity <= 0:
            return False, "Order quantity must be positive"

        return True, "Order approved"

    def calculate_position_size(
        self, ticker: str, price: float, portfolio: PortfolioSummary
    ) -> float:
        """Calculate max allowed quantity based on risk limits."""
        if price <= 0 or portfolio.total_value <= 0:
            return 0.0

        max_value = portfolio.total_value * self.limits.max_position_pct

        existing_value = 0.0
        for pos in portfolio.positions:
            if pos.ticker == ticker:
                existing_value = pos.market_value
                break

        remaining_allocation = max(0.0, max_value - existing_value)
        cash_limited = min(remaining_allocation, portfolio.cash)
        max_quantity = floor(cash_limited / price)

        return max(0.0, float(max_quantity))

    def update_trailing_stops(self, positions: list[PositionInfo]) -> list[Order]:
        """Check trailing stops and return sell orders if triggered."""
        if self.limits.trailing_stop_pct is None:
            return []

        orders: list[Order] = []
        for pos in positions:
            ticker = pos.ticker

            # Update high water mark
            if ticker not in self._high_water_marks:
                self._high_water_marks[ticker] = pos.current_price
            else:
                self._high_water_marks[ticker] = max(
                    self._high_water_marks[ticker], pos.current_price
                )

            high = self._high_water_marks[ticker]
            stop_price = high * (1.0 - self.limits.trailing_stop_pct)
            self._trailing_stops[ticker] = stop_price

            if pos.current_price <= stop_price:
                orders.append(
                    Order(
                        ticker=ticker,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=pos.quantity,
                        price=pos.current_price,
                    )
                )
                # Reset tracking after triggering
                del self._high_water_marks[ticker]
                del self._trailing_stops[ticker]

        return orders

    def check_take_profit(self, positions: list[PositionInfo]) -> list[Order]:
        """Check take profit levels and return sell orders if triggered."""
        if self.limits.take_profit_pct is None:
            return []

        orders: list[Order] = []
        for pos in positions:
            if pos.avg_cost <= 0:
                continue
            gain_pct = (pos.current_price - pos.avg_cost) / pos.avg_cost
            if gain_pct >= self.limits.take_profit_pct:
                orders.append(
                    Order(
                        ticker=pos.ticker,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=pos.quantity,
                        price=pos.current_price,
                    )
                )

        return orders

    def check_daily_loss_limit(self, portfolio: PortfolioSummary) -> bool:
        """Returns True if daily loss limit has been hit."""
        if self.daily_starting_value is None:
            self.daily_starting_value = portfolio.total_value
            return False

        if self.daily_starting_value <= 0:
            return False

        daily_loss_pct = (
            (self.daily_starting_value - portfolio.total_value)
            / self.daily_starting_value
        )
        return daily_loss_pct >= self.limits.max_daily_loss_pct

    def reset_daily(self, portfolio: PortfolioSummary) -> None:
        """Reset daily tracking. Call at start of each trading day."""
        self.daily_starting_value = portfolio.total_value
