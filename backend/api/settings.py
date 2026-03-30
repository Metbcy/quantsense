"""Settings endpoints – watchlist and app configuration."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models.database import get_db
from models.pydantic_models import (
    SettingResponse,
    SettingUpdate,
    TickerCreate,
    TickerResponse,
)
from models.schemas import AppSetting, Watchlist

router = APIRouter()


# ── Watchlist ────────────────────────────────────────────────────────


@router.get("/watchlist", response_model=list[TickerResponse])
async def get_watchlist(db: Session = Depends(get_db)):
    """Get all tickers in the watchlist."""
    return db.query(Watchlist).order_by(Watchlist.added_at.desc()).all()


@router.post("/watchlist", response_model=TickerResponse, status_code=201)
async def add_to_watchlist(req: TickerCreate, db: Session = Depends(get_db)):
    """Add a ticker to the watchlist."""
    ticker_upper = req.ticker.upper()
    existing = db.query(Watchlist).filter(Watchlist.ticker == ticker_upper).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"'{ticker_upper}' is already in the watchlist")

    entry = Watchlist(ticker=ticker_upper, name=req.name)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, db: Session = Depends(get_db)):
    """Remove a ticker from the watchlist."""
    entry = db.query(Watchlist).filter(Watchlist.ticker == ticker.upper()).first()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found in watchlist")

    db.delete(entry)
    db.commit()
    return {"detail": f"'{ticker.upper()}' removed from watchlist"}


# ── App Settings ─────────────────────────────────────────────────────


@router.get("/config", response_model=list[SettingResponse])
async def get_config(db: Session = Depends(get_db)):
    """Get all app settings."""
    return db.query(AppSetting).all()


@router.put("/config", response_model=SettingResponse)
async def update_config(req: SettingUpdate, db: Session = Depends(get_db)):
    """Create or update an app setting."""
    setting = db.query(AppSetting).filter(AppSetting.key == req.key).first()
    if setting:
        setting.value = req.value
    else:
        setting = AppSetting(key=req.key, value=req.value)
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return setting
