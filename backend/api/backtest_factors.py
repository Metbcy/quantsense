"""Fama-French factor exposure endpoint.

Companion to :mod:`api.backtest`. Computes factor decomposition (3-, 5-, or
Carhart-4) of a saved backtest's daily returns or an explicit
returns/dates series. See :mod:`engine.factors` for the regression
machinery and the alpha-after-risk-premia interpretation.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from engine.factors import FactorModel, compute_factor_exposure
from models.database import get_db
from models.schemas import BacktestResult as BacktestResultModel

router = APIRouter()
logger = logging.getLogger(__name__)


class FactorExposureRequest(BaseModel):
    """Either ``result_id`` (look up a saved backtest) OR an explicit
    ``returns`` + ``dates`` pair must be supplied."""

    result_id: int | None = None
    returns: list[float] | None = None
    dates: list[date] | None = None
    model: FactorModel = Field(default="ff3")
    risk_free_subtract: bool = True

    @model_validator(mode="after")
    def _check_inputs(self) -> "FactorExposureRequest":
        has_id = self.result_id is not None
        has_explicit = self.returns is not None and self.dates is not None
        if has_id == has_explicit:
            raise ValueError(
                "exactly one of {result_id, (returns + dates)} must be provided"
            )
        if has_explicit:
            if len(self.returns or []) != len(self.dates or []):
                raise ValueError(
                    "returns and dates must have the same length "
                    f"(got {len(self.returns or [])} vs {len(self.dates or [])})"
                )
            if len(self.returns or []) < 2:
                raise ValueError("need at least 2 observations")
        return self


def _returns_from_backtest(result: BacktestResultModel) -> pd.Series:
    """Build a daily-return series from the trade ledger of a saved backtest.

    The backtest table stores trades but not the equity curve; we
    reconstruct an end-of-day cash+position value series from the trades
    against the saved initial capital, then take simple daily returns.
    For trade-light strategies (one trade) this yields a near-zero return
    series — acceptable, and the regression will surface a low n_obs in
    that case.
    """
    cash = float(result.initial_capital)
    qty = 0.0
    last_price = 0.0
    by_date: dict[date, float] = {}

    sorted_trades = sorted(result.trades, key=lambda t: t.date)
    for tr in sorted_trades:
        if tr.side == "buy":
            cash -= tr.value
            qty += tr.quantity
        else:
            cash += tr.value
            qty -= tr.quantity
        last_price = tr.price
        by_date[tr.date] = cash + qty * last_price

    if not by_date:
        # Fall back to a flat curve [initial, final]
        idx = pd.date_range(result.start_date, result.end_date, freq="B")
        if len(idx) < 2:
            raise HTTPException(
                status_code=400, detail="backtest has too few daily observations"
            )
        equity = np.linspace(
            float(result.initial_capital), float(result.final_value), len(idx)
        )
        s = pd.Series(equity, index=idx.date)
        return s.pct_change().dropna()

    s = pd.Series(by_date).sort_index()
    s.index = pd.Index([d for d in s.index])
    rets = s.pct_change().dropna()
    if len(rets) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "saved backtest produced fewer than 2 daily returns; "
                "supply explicit returns/dates instead"
            ),
        )
    return rets


@router.post("/factor-exposure")
async def factor_exposure(
    req: FactorExposureRequest, db: Session = Depends(get_db)
) -> dict:
    """Decompose strategy returns into Fama-French factor loadings.

    Body fields::

        {
          "result_id": 42,                          # OR
          "returns": [0.001, -0.002, ...],          # fractional daily returns
          "dates":   ["2020-01-02", "2020-01-03"],  # ISO dates, same length
          "model": "ff3" | "ff5" | "carhart4",
          "risk_free_subtract": true                # default
        }

    Returns the :class:`engine.factors.FactorExposure` as a dict with
    annualized alpha (% / year), per-factor coefficient + HC1 SE + t-stat
    + p-value, R², adjusted R², and n_obs.
    """
    if req.result_id is not None:
        result = (
            db.query(BacktestResultModel)
            .filter(BacktestResultModel.id == req.result_id)
            .first()
        )
        if result is None:
            raise HTTPException(
                status_code=404, detail=f"backtest {req.result_id} not found"
            )
        try:
            series = _returns_from_backtest(result)
        except HTTPException:
            raise
        except Exception:
            logger.exception(
                "failed to reconstruct returns for backtest %s", req.result_id
            )
            raise HTTPException(
                status_code=500,
                detail="failed to reconstruct return series from saved backtest",
            )
    else:
        series = pd.Series(req.returns, index=pd.Index(req.dates))

    try:
        exposure = compute_factor_exposure(
            series,
            model=req.model,
            risk_free_subtract=req.risk_free_subtract,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("factor exposure regression failed")
        raise HTTPException(status_code=500, detail="failed to fit factor regression")

    return exposure.to_dict()
