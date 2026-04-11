from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from typing import Generator

from config.settings import settings

# Naming convention so Alembic batch mode always has constraint names
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


_db_initialized = False


def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    from models.schemas import (  # noqa: F401
        User,
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
        PortfolioSnapshot,
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
