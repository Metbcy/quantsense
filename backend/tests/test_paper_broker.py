"""Tests for the PaperBroker — order execution, positions, and portfolio tracking."""
import pytest
from trading.paper_broker import PaperBroker
from trading.broker import Order, OrderSide, OrderType, OrderStatus


@pytest.fixture
def broker():
    return PaperBroker(initial_cash=100000.0)


@pytest.fixture
def broker_with_prices(broker):
    """Set up broker with known prices — sets internal state directly (no async needed)."""
    broker._current_prices.update({"AAPL": 150.0, "GOOG": 2800.0, "TSLA": 250.0})
    return broker


# --- Market orders ---

@pytest.mark.asyncio
async def test_buy_market_order(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    result = await broker.submit_order(order)

    assert result.status == OrderStatus.FILLED
    assert result.filled_price == 150.0
    assert result.filled_quantity == 10
    assert broker.cash == 100000.0 - 1500.0
    assert "AAPL" in broker.positions
    assert broker.positions["AAPL"]["quantity"] == 10
    assert broker.positions["AAPL"]["avg_cost"] == 150.0


@pytest.mark.asyncio
async def test_sell_market_order(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    sell = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=5)
    result = await broker.submit_order(sell)

    assert result.status == OrderStatus.FILLED
    assert broker.positions["AAPL"]["quantity"] == 5
    assert broker.cash == 100000.0 - 1500.0 + 750.0


@pytest.mark.asyncio
async def test_sell_all_removes_position(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    sell = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(sell)

    assert "AAPL" not in broker.positions


@pytest.mark.asyncio
async def test_buy_insufficient_cash(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="GOOG", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1000)
    result = await broker.submit_order(order)

    assert result.status == OrderStatus.REJECTED
    assert "Insufficient cash" in result.message


@pytest.mark.asyncio
async def test_sell_no_position(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10)
    result = await broker.submit_order(order)

    assert result.status == OrderStatus.REJECTED
    assert "No position" in result.message


@pytest.mark.asyncio
async def test_sell_more_than_held(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5)
    await broker.submit_order(buy)

    sell = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10)
    result = await broker.submit_order(sell)

    assert result.status == OrderStatus.REJECTED
    assert "Insufficient shares" in result.message


@pytest.mark.asyncio
async def test_buy_no_price_available(broker):
    order = Order(ticker="UNKNOWN", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    result = await broker.submit_order(order)

    assert result.status == OrderStatus.REJECTED
    assert "No price available" in result.message


# --- Average cost calculation ---

@pytest.mark.asyncio
async def test_avg_cost_on_second_buy(broker_with_prices):
    broker = broker_with_prices
    buy1 = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy1)

    await broker.update_prices({"AAPL": 200.0})
    buy2 = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy2)

    pos = broker.positions["AAPL"]
    assert pos["quantity"] == 20
    assert abs(pos["avg_cost"] - 175.0) < 0.01


# --- Realized PnL ---

@pytest.mark.asyncio
async def test_sell_realized_pnl(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    await broker.update_prices({"AAPL": 200.0})
    sell = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(sell)

    last_trade = broker.trades[-1]
    assert last_trade["realized_pnl"] == (200.0 - 150.0) * 10


# --- Limit orders ---

@pytest.mark.asyncio
async def test_limit_buy_fills_at_or_below(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=160.0)
    result = await broker.submit_order(order)

    assert result.status == OrderStatus.FILLED
    assert result.filled_price == 150.0


@pytest.mark.asyncio
async def test_limit_buy_goes_pending(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=140.0)
    result = await broker.submit_order(order)

    assert result.status == OrderStatus.PENDING
    assert len(broker.pending_orders) == 1


@pytest.mark.asyncio
async def test_pending_limit_fills_on_price_update(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=140.0)
    await broker.submit_order(order)

    await broker.update_prices({"AAPL": 140.0})

    assert len(broker.pending_orders) == 0
    assert "AAPL" in broker.positions
    assert broker.positions["AAPL"]["quantity"] == 10


# --- Stop orders ---

@pytest.mark.asyncio
async def test_stop_sell_goes_pending(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    stop = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.STOP, quantity=10, stop_price=140.0)
    result = await broker.submit_order(stop)

    assert result.status == OrderStatus.PENDING


@pytest.mark.asyncio
async def test_stop_sell_triggers_on_price_drop(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    stop = Order(ticker="AAPL", side=OrderSide.SELL, order_type=OrderType.STOP, quantity=10, stop_price=140.0)
    await broker.submit_order(stop)

    await broker.update_prices({"AAPL": 130.0})

    assert len(broker.pending_orders) == 0
    assert "AAPL" not in broker.positions


# --- Cancel orders ---

@pytest.mark.asyncio
async def test_cancel_pending_order(broker_with_prices):
    broker = broker_with_prices
    order = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10, price=100.0)
    result = await broker.submit_order(order)

    cancelled = await broker.cancel_order(result.order_id)
    assert cancelled is True
    assert len(broker.pending_orders) == 0


@pytest.mark.asyncio
async def test_cancel_nonexistent_order(broker):
    cancelled = await broker.cancel_order("FAKE-ID")
    assert cancelled is False


# --- Portfolio and positions ---

@pytest.mark.asyncio
async def test_portfolio_summary(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    portfolio = await broker.get_portfolio()

    assert portfolio.cash == 100000.0 - 1500.0
    assert portfolio.positions_value == 1500.0
    assert portfolio.total_value == 100000.0
    assert len(portfolio.positions) == 1


@pytest.mark.asyncio
async def test_portfolio_unrealized_pnl(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    await broker.update_prices({"AAPL": 200.0})
    positions = await broker.get_positions()

    assert len(positions) == 1
    assert positions[0].current_price == 200.0
    assert positions[0].unrealized_pnl == 500.0


@pytest.mark.asyncio
async def test_trade_history_tracks_orders(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    history = await broker.get_trade_history()
    assert len(history) == 1
    assert history[0]["ticker"] == "AAPL"
    assert history[0]["side"] == "buy"


@pytest.mark.asyncio
async def test_portfolio_value_history(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    history = broker.get_portfolio_value_history()
    assert len(history) >= 1


# --- Reset ---

@pytest.mark.asyncio
async def test_reset_clears_state(broker_with_prices):
    broker = broker_with_prices
    buy = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    await broker.submit_order(buy)

    broker.reset(initial_cash=50000.0)

    assert broker.cash == 50000.0
    assert len(broker.positions) == 0
    assert len(broker.trades) == 0
    assert len(broker.pending_orders) == 0


# --- Multiple tickers ---

@pytest.mark.asyncio
async def test_multiple_positions(broker_with_prices):
    broker = broker_with_prices
    buy_aapl = Order(ticker="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10)
    buy_tsla = Order(ticker="TSLA", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5)
    await broker.submit_order(buy_aapl)
    await broker.submit_order(buy_tsla)

    assert len(broker.positions) == 2
    assert broker.cash == 100000.0 - 1500.0 - 1250.0

    portfolio = await broker.get_portfolio()
    assert portfolio.positions_value == 1500.0 + 1250.0
