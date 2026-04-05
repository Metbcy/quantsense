"""Tests for the RiskManager — position limits, daily loss, trailing stops, take profit."""
import pytest
from trading.risk_manager import RiskManager, RiskLimits
from trading.broker import Order, OrderSide, OrderType, PortfolioSummary, PositionInfo


def make_portfolio(
    total_value=100000.0,
    cash=100000.0,
    positions=None,
    daily_pnl=0.0,
) -> PortfolioSummary:
    return PortfolioSummary(
        total_value=total_value,
        cash=cash,
        positions_value=total_value - cash,
        total_pnl=0.0,
        total_pnl_pct=0.0,
        positions=positions or [],
        daily_pnl=daily_pnl,
    )


def make_position(ticker="AAPL", quantity=10, avg_cost=150.0, current_price=150.0):
    market_value = quantity * current_price
    cost_basis = quantity * avg_cost
    return PositionInfo(
        ticker=ticker,
        quantity=quantity,
        avg_cost=avg_cost,
        current_price=current_price,
        unrealized_pnl=market_value - cost_basis,
        unrealized_pnl_pct=((market_value - cost_basis) / cost_basis * 100) if cost_basis else 0,
        market_value=market_value,
    )


# --- Basic order checks ---

def test_buy_order_approved():
    rm = RiskManager()
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10, price=150.0)
    portfolio = make_portfolio(cash=100000.0)

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is True
    assert "approved" in reason.lower()


def test_buy_insufficient_cash():
    rm = RiskManager()
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1000, price=150.0)
    portfolio = make_portfolio(cash=5000.0, total_value=5000.0)

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "Insufficient cash" in reason


def test_sell_approved():
    rm = RiskManager()
    pos = make_position(quantity=10)
    order = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=5, price=150.0)
    portfolio = make_portfolio(cash=98500.0, total_value=100000.0, positions=[pos])

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is True


def test_sell_no_position():
    rm = RiskManager()
    order = Order(ticker="GOOG", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=5, price=150.0)
    portfolio = make_portfolio()

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "No position" in reason


def test_sell_more_than_held():
    rm = RiskManager()
    pos = make_position(quantity=5)
    order = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10, price=150.0)
    portfolio = make_portfolio(cash=99250.0, total_value=100000.0, positions=[pos])

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "Cannot sell" in reason


def test_zero_quantity_rejected():
    rm = RiskManager()
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0, price=150.0)
    portfolio = make_portfolio()

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "positive" in reason.lower()


# --- Position concentration ---

def test_position_concentration_limit():
    rm = RiskManager(RiskLimits(max_position_pct=0.25))
    # Trying to buy $30k of AAPL in a $100k portfolio (30% > 25%)
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=200, price=150.0)
    portfolio = make_portfolio(cash=100000.0, total_value=100000.0)

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "Position too large" in reason


def test_position_concentration_with_existing_position():
    rm = RiskManager(RiskLimits(max_position_pct=0.25))
    # Already hold $20k of AAPL, trying to add $10k more ($30k total = 30% > 25%)
    existing = make_position(quantity=100, avg_cost=200.0, current_price=200.0)  # $20k
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=50, price=200.0)
    portfolio = make_portfolio(cash=80000.0, total_value=100000.0, positions=[existing])

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False


def test_position_within_limit():
    rm = RiskManager(RiskLimits(max_position_pct=0.25))
    # Buying $20k in a $100k portfolio (20% < 25%)
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100, price=200.0)
    portfolio = make_portfolio(cash=100000.0, total_value=100000.0)

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is True


# --- Max open positions ---

def test_max_open_positions():
    rm = RiskManager(RiskLimits(max_open_positions=2))
    pos1 = make_position(ticker="AAPL", quantity=10, current_price=150.0)
    pos2 = make_position(ticker="GOOG", quantity=5, current_price=2800.0)

    order = Order(ticker="TSLA", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1, price=250.0)
    portfolio = make_portfolio(cash=50000.0, total_value=100000.0, positions=[pos1, pos2])

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "Max open positions" in reason


def test_adding_to_existing_position_not_blocked_by_max():
    rm = RiskManager(RiskLimits(max_open_positions=1))
    pos = make_position(ticker="AAPL", quantity=10, current_price=150.0)

    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5, price=150.0)
    portfolio = make_portfolio(cash=99000.0, total_value=100000.0, positions=[pos])

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is True


# --- Daily loss limit ---

def test_daily_loss_limit_not_hit():
    rm = RiskManager(RiskLimits(max_daily_loss_pct=0.05))
    portfolio = make_portfolio(total_value=99000.0)

    # First call sets starting value
    assert rm.check_daily_loss_limit(portfolio) is False
    # Second call: lost $1k on $99k starting (1% < 5%)
    portfolio2 = make_portfolio(total_value=98000.0)
    assert rm.check_daily_loss_limit(portfolio2) is False


def test_daily_loss_limit_triggered():
    rm = RiskManager(RiskLimits(max_daily_loss_pct=0.05))
    portfolio = make_portfolio(total_value=100000.0)
    rm.check_daily_loss_limit(portfolio)  # sets starting value

    # Lost 6%
    portfolio2 = make_portfolio(total_value=94000.0)
    assert rm.check_daily_loss_limit(portfolio2) is True


def test_daily_loss_blocks_buy():
    rm = RiskManager(RiskLimits(max_daily_loss_pct=0.05))
    # Initialize starting value
    rm.daily_starting_value = 100000.0

    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10, price=150.0)
    # Portfolio now at $93k -> 7% loss
    portfolio = make_portfolio(total_value=93000.0, cash=93000.0)

    allowed, reason = rm.check_order(order, portfolio)
    assert allowed is False
    assert "Daily loss limit" in reason


def test_reset_daily():
    rm = RiskManager()
    portfolio = make_portfolio(total_value=95000.0)
    rm.reset_daily(portfolio)
    assert rm.daily_starting_value == 95000.0


# --- Position sizing ---

def test_calculate_position_size():
    rm = RiskManager(RiskLimits(max_position_pct=0.25))
    portfolio = make_portfolio(cash=100000.0, total_value=100000.0)

    qty = rm.calculate_position_size("AAPL", 150.0, portfolio)
    # Max allocation = 25k, so 25000/150 = 166 shares
    assert qty == 166.0


def test_position_size_accounts_for_existing():
    rm = RiskManager(RiskLimits(max_position_pct=0.25))
    existing = make_position(ticker="AAPL", quantity=100, avg_cost=150.0, current_price=150.0)
    portfolio = make_portfolio(cash=85000.0, total_value=100000.0, positions=[existing])

    qty = rm.calculate_position_size("AAPL", 150.0, portfolio)
    # Max = 25k, existing = 15k, remaining = 10k, 10000/150 = 66
    assert qty == 66.0


def test_position_size_zero_price():
    rm = RiskManager()
    portfolio = make_portfolio()
    assert rm.calculate_position_size("AAPL", 0.0, portfolio) == 0.0


def test_position_size_limited_by_cash():
    rm = RiskManager(RiskLimits(max_position_pct=0.5))
    # 50% of 100k = 50k, but only 10k cash
    portfolio = make_portfolio(cash=10000.0, total_value=100000.0)

    qty = rm.calculate_position_size("AAPL", 150.0, portfolio)
    assert qty == 66.0  # floor(10000 / 150)


# --- Trailing stops ---

def test_trailing_stop_not_triggered():
    rm = RiskManager(RiskLimits(trailing_stop_pct=0.10))
    pos = make_position(ticker="AAPL", quantity=10, avg_cost=150.0, current_price=160.0)

    orders = rm.update_trailing_stops([pos])
    assert len(orders) == 0
    assert rm._high_water_marks["AAPL"] == 160.0


def test_trailing_stop_triggered():
    rm = RiskManager(RiskLimits(trailing_stop_pct=0.10))

    # Price goes up to 200
    pos_up = make_position(ticker="AAPL", quantity=10, current_price=200.0)
    rm.update_trailing_stops([pos_up])
    assert rm._high_water_marks["AAPL"] == 200.0

    # Price drops to 175 (12.5% from 200 > 10% trailing)
    pos_down = make_position(ticker="AAPL", quantity=10, current_price=175.0)
    orders = rm.update_trailing_stops([pos_down])

    assert len(orders) == 1
    assert orders[0].ticker == "AAPL"
    assert orders[0].side == OrderSide.SELL
    assert orders[0].quantity == 10


def test_trailing_stop_disabled():
    rm = RiskManager(RiskLimits(trailing_stop_pct=None))
    pos = make_position(current_price=50.0)
    assert rm.update_trailing_stops([pos]) == []


# --- Take profit ---

def test_take_profit_triggered():
    rm = RiskManager(RiskLimits(take_profit_pct=0.20))
    pos = make_position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=125.0)

    orders = rm.check_take_profit([pos])
    assert len(orders) == 1
    assert orders[0].ticker == "AAPL"
    assert orders[0].side == OrderSide.SELL


def test_take_profit_not_triggered():
    rm = RiskManager(RiskLimits(take_profit_pct=0.20))
    pos = make_position(ticker="AAPL", quantity=10, avg_cost=100.0, current_price=110.0)

    orders = rm.check_take_profit([pos])
    assert len(orders) == 0


def test_take_profit_disabled():
    rm = RiskManager(RiskLimits(take_profit_pct=None))
    pos = make_position(current_price=999.0)
    assert rm.check_take_profit([pos]) == []
