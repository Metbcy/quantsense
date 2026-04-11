"""Tests for portfolio snapshot persistence."""
import pytest
from datetime import datetime
from models.schemas import Portfolio as PortfolioDB, PortfolioSnapshot


def test_create_snapshot(db_session):
    """Snapshot can be created and queried."""
    portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
    db_session.add(portfolio)
    db_session.commit()

    snap = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        total_value=105000.0,
        cash=50000.0,
        positions_value=55000.0,
        recorded_at=datetime(2026, 4, 10, 12, 0, 0),
    )
    db_session.add(snap)
    db_session.commit()

    result = db_session.query(PortfolioSnapshot).filter_by(portfolio_id=portfolio.id).first()
    assert result is not None
    assert result.total_value == 105000.0
    assert result.cash == 50000.0
    assert result.positions_value == 55000.0


def test_snapshots_ordered_by_time(db_session):
    """Multiple snapshots returned in chronological order."""
    portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
    db_session.add(portfolio)
    db_session.commit()

    for i, val in enumerate([100000, 101000, 99500]):
        snap = PortfolioSnapshot(
            portfolio_id=portfolio.id,
            total_value=val,
            cash=50000.0,
            positions_value=val - 50000.0,
            recorded_at=datetime(2026, 4, 10, 10 + i, 0, 0),
        )
        db_session.add(snap)
    db_session.commit()

    snaps = (
        db_session.query(PortfolioSnapshot)
        .filter_by(portfolio_id=portfolio.id)
        .order_by(PortfolioSnapshot.recorded_at.asc())
        .all()
    )
    assert len(snaps) == 3
    assert snaps[0].total_value == 100000
    assert snaps[2].total_value == 99500
