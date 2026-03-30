from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from typing import Generator

from config.settings import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


_db_initialized = False


def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    from models.schemas import (  # noqa: F401
        Watchlist,
        OHLCVData,
        SentimentRecord,
        SentimentAggregate,
        Strategy,
        BacktestResult,
        BacktestTrade,
        Portfolio,
        Position,
        Trade,
        AppSetting,
    )
    Base.metadata.create_all(bind=engine)
    _db_initialized = True


def get_db() -> Generator:
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
