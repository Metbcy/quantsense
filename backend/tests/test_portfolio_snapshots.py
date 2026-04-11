"""Tests for portfolio snapshot persistence."""
import pytest
from datetime import datetime, UTC
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


from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from models.database import Base


def test_history_endpoint_returns_points():
    """GET /api/portfolio/history returns snapshot points filtered by period."""
    from models.database import get_db
    from fastapi import FastAPI
    from api.portfolio_history import router

    # Use StaticPool so all connections share the same in-memory DB,
    # including those made from TestClient's background thread.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
        session.add(portfolio)
        session.commit()

        now = datetime.now(UTC)
        for i in range(48):
            snap = PortfolioSnapshot(
                portfolio_id=portfolio.id,
                total_value=100000 + i * 100,
                cash=50000.0,
                positions_value=50000 + i * 100,
                recorded_at=now - timedelta(hours=48 - i),
            )
            session.add(snap)
        session.commit()

        app = FastAPI()
        app.dependency_overrides[get_db] = lambda: session
        app.include_router(router, prefix="/api/portfolio")
        client = TestClient(app)

        res = client.get("/api/portfolio/history?period=1W")
        assert res.status_code == 200
        data = res.json()
        assert "points" in data
        assert len(data["points"]) == 48

        res = client.get("/api/portfolio/history?period=1M")
        assert res.status_code == 200
        assert len(res.json()["points"]) == 48
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
