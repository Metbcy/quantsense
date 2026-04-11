"""Portfolio history endpoint — serves time-series of portfolio snapshots."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from models.database import get_db
from models.schemas import Portfolio as PortfolioDB, PortfolioSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()

PERIOD_DELTAS = {
    "1W": timedelta(weeks=1),
    "1M": timedelta(days=30),
    "3M": timedelta(days=90),
    "1Y": timedelta(days=365),
}

MAX_POINTS = 200


@router.get("/history")
def get_portfolio_history(
    period: str = Query("1M", pattern="^(1W|1M|3M|1Y|all)$"),
    db: Session = Depends(get_db),
):
    """Return portfolio value history for the given period."""
    portfolio = db.query(PortfolioDB).filter(PortfolioDB.name == "default").first()
    if not portfolio:
        return {"points": []}

    query = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.portfolio_id == portfolio.id)
    )

    if period != "all":
        cutoff = datetime.utcnow() - PERIOD_DELTAS[period]
        query = query.filter(PortfolioSnapshot.recorded_at >= cutoff)

    query = query.order_by(PortfolioSnapshot.recorded_at.asc())
    snapshots = query.all()

    # Downsample if too many points
    if len(snapshots) > MAX_POINTS:
        stride = len(snapshots) / MAX_POINTS
        sampled = []
        for i in range(MAX_POINTS):
            idx = int(i * stride)
            sampled.append(snapshots[idx])
        if sampled[-1] != snapshots[-1]:
            sampled[-1] = snapshots[-1]
        snapshots = sampled

    return {
        "points": [
            {
                "timestamp": s.recorded_at.isoformat(),
                "total_value": s.total_value,
                "cash": s.cash,
            }
            for s in snapshots
        ]
    }
