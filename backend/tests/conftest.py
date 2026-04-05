"""Shared test fixtures for QuantSense backend tests."""
import os
import sys
import pytest

# Ensure backend root is on sys.path so imports like `from trading.broker import ...` work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Force SQLite in-memory DB for all tests
os.environ["DATABASE_URL"] = "sqlite:///./test_quantsense.db"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.database import Base


@pytest.fixture()
def db_session():
    """Create an isolated in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
