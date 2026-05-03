"""Multi-asset portfolio backtest endpoint.

Mirrors the conventions of :mod:`api.backtest` (single-asset):

* Pydantic request body, hand-validated where the engine's config has
  stricter invariants than Pydantic can express.
* OHLCV pulled via ``data.shared.provider`` (the same cached
  YahooFinanceProvider used by the rest of the API).
* Response is the result dataclass flattened into a JSON-friendly dict
  plus the ``run_hash`` reproducibility token.

The auth + rate-limit story matches ``api.backtest``: there are no
per-route auth decorators on the existing single-asset routes (auth is
configured globally / per-app), and rate limiting is applied at the
FastAPI app level via slowapi's ``default_limits``. We follow the same
pattern.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from data.provider import OHLCVBar
from data.shared import provider
from engine.portfolio import (
    PortfolioBacktestConfig,
    PortfolioBacktestResult,
    run_portfolio_backtest,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Hard cap on the number of equity-curve points returned to the client.
# Long backtests get downsampled by stride to fit within the cap so the
# response payload stays bounded.
_EQUITY_CURVE_MAX_POINTS = 2000


class PortfolioBacktestRequest(BaseModel):
    """Request body for ``POST /api/backtest/portfolio``.

    ``weights == None`` selects equal-weight across ``tickers``.
    Otherwise the dict must have one entry per ticker and sum to 1.0
    (validated server-side by the engine).
    """

    model_config = ConfigDict(extra="forbid")

    tickers: list[str] = Field(..., min_length=1, max_length=50)
    weights: dict[str, float] | None = None
    start_date: date
    end_date: date
    initial_capital: float = Field(100_000.0, gt=0)
    rebalance_schedule: str = Field("monthly")
    slippage_bps: float = Field(5.0, ge=0)
    commission_per_share: float = Field(0.0, ge=0)
    commission_pct: float = Field(0.0, ge=0)
    benchmark_ticker: str | None = "SPY"
    seed: int = 42


@router.post("/portfolio")
async def run_portfolio(req: PortfolioBacktestRequest) -> dict:
    """Run a multi-asset portfolio backtest.

    The endpoint:

    1. Fetches OHLCV for every requested ticker (and the benchmark, if
       any) in parallel.
    2. Builds a :class:`PortfolioBacktestConfig`, dispatches to
       :func:`run_portfolio_backtest`.
    3. Flattens the result + run_hash into a JSON response, downsampling
       the equity curve if it exceeds ``_EQUITY_CURVE_MAX_POINTS``.
    """
    if req.end_date < req.start_date:
        raise HTTPException(
            status_code=400, detail="end_date must be on/after start_date"
        )
    if len(set(req.tickers)) != len(req.tickers):
        raise HTTPException(status_code=400, detail="Duplicate tickers in request")

    # Fetch OHLCV for every ticker concurrently — keeps wall-clock time
    # roughly equal to the slowest provider call rather than the sum.
    fetch_tickers = list(req.tickers)
    if req.benchmark_ticker and req.benchmark_ticker not in fetch_tickers:
        fetch_tickers.append(req.benchmark_ticker)

    try:
        gathered = await asyncio.gather(
            *(
                provider.get_ohlcv(t, req.start_date, req.end_date)
                for t in fetch_tickers
            )
        )
    except Exception:
        logger.exception("Market data fetch failed for portfolio request")
        raise HTTPException(status_code=500, detail="Failed to fetch market data")

    bars_by_ticker: dict[str, list[OHLCVBar]] = {
        t: bars for t, bars in zip(fetch_tickers, gathered, strict=False)
    }
    missing = [t for t in req.tickers if not bars_by_ticker.get(t)]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No OHLCV data found for {missing} between "
                f"{req.start_date} and {req.end_date}"
            ),
        )

    benchmark_bars: list[OHLCVBar] | None = None
    if req.benchmark_ticker:
        benchmark_bars = bars_by_ticker.get(req.benchmark_ticker) or None

    portfolio_bars = {t: bars_by_ticker[t] for t in req.tickers}

    try:
        config = PortfolioBacktestConfig(
            tickers=list(req.tickers),
            weights=dict(req.weights) if req.weights is not None else None,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            rebalance_schedule=req.rebalance_schedule,  # type: ignore[arg-type]
            slippage_bps=req.slippage_bps,
            commission_per_share=req.commission_per_share,
            commission_pct=req.commission_pct,
            benchmark_ticker=req.benchmark_ticker,
            seed=req.seed,
        )
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        result = run_portfolio_backtest(config, portfolio_bars, benchmark_bars)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Portfolio backtest execution failed")
        raise HTTPException(status_code=500, detail="Portfolio backtest failed")

    return _serialize_result(result)


def _serialize_result(result: PortfolioBacktestResult) -> dict:
    """Convert a :class:`PortfolioBacktestResult` into a JSON-friendly dict.

    Equity curves longer than ``_EQUITY_CURVE_MAX_POINTS`` are
    downsampled by stride; the FIRST and LAST points are always
    preserved so the visible total return matches the metrics block.
    """
    n = len(result.dates)
    if n > _EQUITY_CURVE_MAX_POINTS:
        stride = max(1, n // _EQUITY_CURVE_MAX_POINTS)
        idx = list(range(0, n, stride))
        if idx[-1] != n - 1:
            idx.append(n - 1)
    else:
        idx = list(range(n))

    equity_curve = [
        [result.dates[i].isoformat(), float(result.equity_curve[i])] for i in idx
    ]

    fills = {
        ticker: [
            {
                "date": f.date.isoformat(),
                "side": f.side,
                "quantity": f.quantity,
                "fill_price": f.fill_price,
                "notional": f.notional,
                "commission": f.commission,
                "slippage_cost": f.slippage_cost,
                "reason": f.reason,
            }
            for f in legs
        ]
        for ticker, legs in result.fills.items()
    }

    metrics_obj = result.metrics
    metrics: dict = {
        "total_return_pct": metrics_obj.total_return_pct,
        "annualized_return_pct": getattr(metrics_obj, "annualized_return_pct", None),
        "sharpe_ratio": metrics_obj.sharpe_ratio,
        "sortino_ratio": getattr(metrics_obj, "sortino_ratio", None),
        "calmar_ratio": getattr(metrics_obj, "calmar_ratio", None),
        "max_drawdown_pct": metrics_obj.max_drawdown_pct,
        "max_drawdown_duration_bars": getattr(
            metrics_obj, "max_drawdown_duration_bars", None
        ),
        "downside_deviation": getattr(metrics_obj, "downside_deviation", None),
        "alpha": getattr(metrics_obj, "alpha", None),
        "beta": getattr(metrics_obj, "beta", None),
        "deflated_sharpe_ratio": getattr(metrics_obj, "deflated_sharpe_ratio", None),
    }

    cfg = result.config
    config_dict = {
        "tickers": list(cfg.tickers),
        "weights": dict(cfg.weights) if cfg.weights is not None else None,
        "start_date": cfg.start_date.isoformat(),
        "end_date": cfg.end_date.isoformat(),
        "initial_capital": cfg.initial_capital,
        "rebalance_schedule": cfg.rebalance_schedule,
        "slippage_bps": cfg.slippage_bps,
        "commission_per_share": cfg.commission_per_share,
        "commission_pct": cfg.commission_pct,
        "benchmark_ticker": cfg.benchmark_ticker,
        "seed": cfg.seed,
    }

    return {
        "run_hash": result.run_hash,
        "config": config_dict,
        "metrics": metrics,
        "equity_curve": equity_curve,
        "equity_curve_full_length": n,
        "equity_curve_returned_length": len(equity_curve),
        "final_cash": result.final_cash,
        "final_positions": result.final_positions,
        "total_turnover": result.total_turnover,
        "per_ticker_pnl": result.per_ticker_pnl,
        "fills": fills,
        "benchmark_equity_curve": [
            [d.isoformat(), float(v)] for d, v in result.benchmark_equity_curve
        ],
    }
