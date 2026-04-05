"""Tests for paper broker DB persistence — state survives save/load cycles."""
import pytest
from models.schemas import Portfolio as PortfolioDB, Position as PositionDB, Trade as TradeDB
from trading.paper_broker import PaperBroker


def _get_or_create_portfolio(db) -> PortfolioDB:
    portfolio = db.query(PortfolioDB).filter(PortfolioDB.name == "default").first()
    if not portfolio:
        portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def _save_broker_to_db(db, broker: PaperBroker):
    """Replicates the save logic from api/trading.py."""
    portfolio = _get_or_create_portfolio(db)
    portfolio.cash = broker.cash

    db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).delete()
    for ticker, pos_data in broker.positions.items():
        current_price = broker._current_prices.get(ticker, pos_data["avg_cost"])
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


def _load_broker_from_db(db) -> PaperBroker:
    """Replicates the load logic from api/trading.py."""
    portfolio = _get_or_create_portfolio(db)
    broker = PaperBroker(initial_cash=portfolio.initial_cash)
    broker.cash = portfolio.cash

    positions = db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).all()
    for pos in positions:
        if pos.quantity > 0:
            broker.positions[pos.ticker] = {
                "quantity": pos.quantity,
                "avg_cost": pos.avg_cost,
            }
            if pos.current_price and pos.current_price > 0:
                broker._current_prices[pos.ticker] = pos.current_price

    return broker


def test_empty_portfolio_round_trip(db_session):
    broker = PaperBroker(initial_cash=100000.0)
    _save_broker_to_db(db_session, broker)
    loaded = _load_broker_from_db(db_session)

    assert loaded.cash == 100000.0
    assert loaded.initial_cash == 100000.0
    assert len(loaded.positions) == 0


def test_positions_round_trip(db_session):
    broker = PaperBroker(initial_cash=100000.0)
    broker.cash = 85000.0
    broker.positions["AAPL"] = {"quantity": 50, "avg_cost": 150.0}
    broker.positions["GOOG"] = {"quantity": 5, "avg_cost": 2800.0}
    broker._current_prices["AAPL"] = 160.0
    broker._current_prices["GOOG"] = 2900.0

    _save_broker_to_db(db_session, broker)
    loaded = _load_broker_from_db(db_session)

    assert loaded.cash == 85000.0
    assert len(loaded.positions) == 2
    assert loaded.positions["AAPL"]["quantity"] == 50
    assert loaded.positions["AAPL"]["avg_cost"] == 150.0
    assert loaded.positions["GOOG"]["quantity"] == 5


def test_current_prices_restored(db_session):
    """Verify that current_price is saved and restored, not just avg_cost."""
    broker = PaperBroker(initial_cash=100000.0)
    broker.cash = 98500.0
    broker.positions["AAPL"] = {"quantity": 10, "avg_cost": 150.0}
    broker._current_prices["AAPL"] = 200.0  # Price moved up

    _save_broker_to_db(db_session, broker)
    loaded = _load_broker_from_db(db_session)

    assert loaded._current_prices["AAPL"] == 200.0


def test_unrealized_pnl_saved_correctly(db_session):
    """Verify unrealized PnL is calculated from current_price, not avg_cost."""
    broker = PaperBroker(initial_cash=100000.0)
    broker.cash = 98500.0
    broker.positions["AAPL"] = {"quantity": 10, "avg_cost": 150.0}
    broker._current_prices["AAPL"] = 200.0

    _save_broker_to_db(db_session, broker)

    portfolio = _get_or_create_portfolio(db_session)
    db_pos = db_session.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).first()

    assert db_pos.current_price == 200.0
    assert db_pos.unrealized_pnl == (200.0 - 150.0) * 10  # $500


def test_save_overwrites_positions(db_session):
    """Saving should replace all positions, not accumulate."""
    broker = PaperBroker(initial_cash=100000.0)
    broker.positions["AAPL"] = {"quantity": 10, "avg_cost": 150.0}
    _save_broker_to_db(db_session, broker)

    # Second save with different positions
    broker.positions = {"GOOG": {"quantity": 5, "avg_cost": 2800.0}}
    broker._current_prices = {"GOOG": 2800.0}
    _save_broker_to_db(db_session, broker)

    loaded = _load_broker_from_db(db_session)
    assert "AAPL" not in loaded.positions
    assert "GOOG" in loaded.positions
    assert len(loaded.positions) == 1


def test_zero_quantity_not_loaded(db_session):
    """Positions with zero quantity should not be loaded."""
    portfolio = _get_or_create_portfolio(db_session)
    db_pos = PositionDB(
        portfolio_id=portfolio.id,
        ticker="DEAD",
        quantity=0,
        avg_cost=100.0,
        current_price=50.0,
        unrealized_pnl=-500.0,
    )
    db_session.add(db_pos)
    db_session.commit()

    loaded = _load_broker_from_db(db_session)
    assert "DEAD" not in loaded.positions
