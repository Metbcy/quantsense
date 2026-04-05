"""Settings endpoints – watchlist and app configuration."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user
from models.database import get_db
from models.pydantic_models import (
    SettingResponse,
    SettingUpdate,
    TickerCreate,
    TickerResponse,
)
from models.schemas import AppSetting, User, Watchlist

router = APIRouter()


def _watchlist_query(db: Session, user: User | None):
    """Base query filtered by user when authenticated."""
    q = db.query(Watchlist)
    if user is not None:
        q = q.filter(Watchlist.user_id == user.id)
    else:
        q = q.filter(Watchlist.user_id.is_(None))
    return q


# ── Watchlist ────────────────────────────────────────────────────────


@router.get("/watchlist", response_model=list[TickerResponse])
async def get_watchlist(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Get all tickers in the watchlist."""
    return _watchlist_query(db, user).order_by(Watchlist.added_at.desc()).all()


@router.post("/watchlist", response_model=TickerResponse, status_code=201)
async def add_to_watchlist(
    req: TickerCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Add a ticker to the watchlist."""
    ticker_upper = req.ticker.upper()
    existing = _watchlist_query(db, user).filter(Watchlist.ticker == ticker_upper).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"'{ticker_upper}' is already in the watchlist")

    entry = Watchlist(ticker=ticker_upper, name=req.name, user_id=user.id if user else None)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(
    ticker: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Remove a ticker from the watchlist."""
    entry = _watchlist_query(db, user).filter(Watchlist.ticker == ticker.upper()).first()
    if entry is None:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found in watchlist")

    db.delete(entry)
    db.commit()
    return {"detail": f"'{ticker.upper()}' removed from watchlist"}


# ── App Settings ─────────────────────────────────────────────────────


@router.get("/config")
async def get_config(db: Session = Depends(get_db)):
    """Get all app settings as a key-value dict."""
    settings = db.query(AppSetting).all()
    return {s.key: s.value for s in settings}


@router.put("/config")
async def update_config(data: dict, db: Session = Depends(get_db)):
    """Bulk create/update app settings from a key-value dict."""
    for key, value in data.items():
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = str(value)
        else:
            setting = AppSetting(key=key, value=str(value))
            db.add(setting)
    db.commit()
    return {"detail": "Settings saved"}
