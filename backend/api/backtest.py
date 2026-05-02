"""Backtest endpoints – run, list, and inspect backtests."""

import csv
import io
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from data.shared import provider
from engine.backtest import BacktestConfig, run_backtest
from engine.optimizer import run_strategy_optimization
from engine.significance import (
    bootstrap_sharpe_ci,
    permutation_test_sharpe,
    returns_from_equity,
)
from engine.strategy import STRATEGY_REGISTRY
from models.database import get_db
from models.pydantic_models import (
    BacktestRequest,
    BacktestResponse,
    BacktestTradeResponse,
    OptimizeRequest,
    OptimizationResponse,
)
from models.schemas import BacktestResult as BacktestResultModel
from models.schemas import BacktestTrade as BacktestTradeModel
from models.schemas import Strategy as StrategyModel

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/run")
async def run(req: BacktestRequest, db: Session = Depends(get_db)):
    """Run a backtest for a given strategy and ticker."""
    # 1. Validate strategy type
    strategy_cls = STRATEGY_REGISTRY.get(req.strategy_type)
    if strategy_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{req.strategy_type}'. "
            f"Available: {list(STRATEGY_REGISTRY.keys())}",
        )

    try:
        strategy = strategy_cls(req.params or None)
    except Exception as exc:
        logger.warning("Invalid strategy params for %s: %s", req.strategy_type, exc)
        raise HTTPException(status_code=400, detail="Invalid strategy parameters")

    # 2. Fetch OHLCV data
    try:
        bars = await provider.get_ohlcv(req.ticker, req.start_date, req.end_date)
    except Exception as exc:
        logger.exception("Market data fetch failed for %s", req.ticker)
        raise HTTPException(status_code=500, detail="Failed to fetch market data")

    if not bars:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data found for {req.ticker} "
            f"between {req.start_date} and {req.end_date}",
        )

    # 3. Run backtest
    config = BacktestConfig(
        ticker=req.ticker,
        strategy=strategy,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        atr_stop_multiplier=req.atr_stop_multiplier,
    )

    try:
        result = run_backtest(config, bars)
    except Exception as exc:
        logger.exception("Backtest execution failed for %s", req.ticker)
        raise HTTPException(status_code=500, detail="Backtest execution failed")

    # 4. Save strategy record
    db_strategy = StrategyModel(
        name=strategy.name,
        type=req.strategy_type,
        params=req.params,
    )
    db.add(db_strategy)
    db.flush()

    # Trade-level stats (computed from trades, not metrics object)
    sell_pnls = [t.pnl for t in result.trades if t.side == "sell"]
    win_rate = (len([p for p in sell_pnls if p > 0]) / len(sell_pnls) * 100.0) if sell_pnls else 0.0
    total_trades = len(sell_pnls)
    initial_capital = result.config.initial_capital
    final_value = result.equity_curve[-1][1] if result.equity_curve else initial_capital

    # 5. Save backtest result
    db_result = BacktestResultModel(
        strategy_id=db_strategy.id,
        ticker=req.ticker,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=initial_capital,
        final_value=final_value,
        total_return_pct=result.metrics.total_return_pct,
        sharpe_ratio=result.metrics.sharpe_ratio,
        max_drawdown_pct=result.metrics.max_drawdown_pct,
        win_rate=win_rate,
        total_trades=total_trades,
    )
    db.add(db_result)
    db.flush()

    # 6. Save trade records
    for t in result.trades:
        db_trade = BacktestTradeModel(
            backtest_id=db_result.id,
            date=t.date,
            side=t.side,
            price=t.price,
            quantity=t.quantity,
            value=t.value,
            pnl=t.pnl,
        )
        db.add(db_trade)

    db.commit()
    db.refresh(db_result)

    # Build response matching frontend expected shape
    return _format_result(db_result, req.strategy_type, result.equity_curve, result.metrics)


@router.post("/optimize")
async def optimize_strategy(req: OptimizeRequest) -> dict:
    """Walk-forward parameter optimization.

    Returns the walk-forward result shape (see engine.walk_forward.to_dict):
    n_windows, oos_sharpe_avg, oos_sharpe_std, is_vs_oos_degradation_pct,
    and per-window detail.
    """
    # 1. Fetch historical data
    bars = await provider.get_ohlcv(req.ticker, req.start_date, req.end_date)
    if not bars:
        raise HTTPException(
            status_code=400,
            detail=f"No OHLCV data found for {req.ticker} between {req.start_date} and {req.end_date}",
        )

    # 2. Run optimization
    try:
        # Convert param_ranges to dict for the optimizer
        param_ranges_dict = {
            name: pr.model_dump() for name, pr in req.param_ranges.items()
        }
        
        result = run_strategy_optimization(
            ticker=req.ticker,
            strategy_type=req.strategy_type,
            bars=bars,
            start_date=req.start_date,
            end_date=req.end_date,
            param_ranges=param_ranges_dict,
            initial_capital=req.initial_capital,
            n_trials=req.n_trials,
            metric=req.metric
        )
        return result
    except Exception as exc:
        logger.exception("Optimization failed for %s", req.ticker)
        raise HTTPException(status_code=500, detail=str(exc))


def _format_result(db_result, strategy_type: str = "", equity_curve=None, metrics_obj=None):
    """Format a DB backtest result into the frontend-expected shape."""
    trades = [
        {
            "date": str(t.date),
            "side": t.side,
            "price": t.price,
            "quantity": t.quantity,
            "value": t.value,
            "pnl": t.pnl,
        }
        for t in db_result.trades
    ]
    # Resolve strategy_type from DB if not passed
    if not strategy_type and db_result.strategy:
        strategy_type = db_result.strategy.type or db_result.strategy.name

    # Compute trade-level metrics from stored trades if not passed from engine
    sell_pnls = [t.pnl for t in db_result.trades if t.pnl != 0]
    avg_pnl = sum(sell_pnls) / len(sell_pnls) if sell_pnls else 0
    best_pnl = max(sell_pnls) if sell_pnls else 0
    worst_pnl = min(sell_pnls) if sell_pnls else 0
    gross_profit = sum(p for p in sell_pnls if p > 0)
    gross_loss = abs(sum(p for p in sell_pnls if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)

    if metrics_obj:
        # New PerformanceMetrics doesn't carry trade-level stats; trade-derived
        # numbers above remain authoritative.
        pass

    # Pull rich quant metrics from the engine result if available.
    quant_extras: dict = {}
    if metrics_obj is not None:
        quant_extras = {
            "annualized_return_pct": getattr(metrics_obj, "annualized_return_pct", None),
            "sortino_ratio": getattr(metrics_obj, "sortino_ratio", None),
            "calmar_ratio": getattr(metrics_obj, "calmar_ratio", None),
            "max_drawdown_duration_bars": getattr(metrics_obj, "max_drawdown_duration_bars", None),
            "downside_deviation": getattr(metrics_obj, "downside_deviation", None),
            "alpha": getattr(metrics_obj, "alpha", None),
            "beta": getattr(metrics_obj, "beta", None),
            "deflated_sharpe_ratio": getattr(metrics_obj, "deflated_sharpe_ratio", None),
        }

    return {
        "id": db_result.id,
        "ticker": db_result.ticker,
        "strategy_type": strategy_type,
        "start_date": str(db_result.start_date),
        "end_date": str(db_result.end_date),
        "created_at": db_result.created_at.isoformat() if db_result.created_at else None,
        "metrics": {
            "initial_capital": db_result.initial_capital,
            "final_value": db_result.final_value,
            "total_return_pct": db_result.total_return_pct,
            "sharpe_ratio": db_result.sharpe_ratio,
            "max_drawdown_pct": db_result.max_drawdown_pct,
            "win_rate": db_result.win_rate,
            "total_trades": db_result.total_trades,
            "avg_trade_pnl": avg_pnl,
            "best_trade_pnl": best_pnl,
            "worst_trade_pnl": worst_pnl,
            "profit_factor": profit_factor,
            **quant_extras,
        },
        "trades": trades,
        "equity_curve": [
            [str(d), v] for d, v in (equity_curve or [])
        ],
    }


@router.get("/results")
async def list_results(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    """List all saved backtest results (paginated)."""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    offset = (page - 1) * page_size

    query = db.query(BacktestResultModel).order_by(BacktestResultModel.created_at.desc())
    total = query.count()
    results = query.offset(offset).limit(page_size).all()

    return {
        "items": [_format_result(r) for r in results],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/results/{result_id}")
async def get_result(result_id: int, db: Session = Depends(get_db)):
    """Get a specific backtest result with its trades."""
    result = db.query(BacktestResultModel).filter(BacktestResultModel.id == result_id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return _format_result(result)


@router.delete("/results/{result_id}")
async def delete_result(result_id: int, db: Session = Depends(get_db)):
    """Delete a backtest result and its trades."""
    result = db.query(BacktestResultModel).filter(BacktestResultModel.id == result_id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    db.query(BacktestTradeModel).filter(BacktestTradeModel.backtest_id == result_id).delete()
    db.delete(result)
    db.commit()
    return {"detail": "Backtest result deleted"}


@router.get("/strategies")
async def list_strategies():
    """List available strategies with default params and descriptions."""
    strategies = []
    for key, cls in STRATEGY_REGISTRY.items():
        instance = cls()
        strategies.append(
            {
                "type": key,
                "name": instance.name,
                "description": instance.description,
                "default_params": instance.default_params(),
            }
        )
    return strategies


@router.post("/compare")
async def compare_strategies(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 100000,
    db: Session = Depends(get_db),
):
    """Run ALL strategies against the same ticker and compare results."""
    # 1. Fetch OHLCV data once
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    try:
        bars = await provider.get_ohlcv(ticker, start, end)
    except Exception:
        logger.exception("Market data fetch failed for %s", ticker)
        raise HTTPException(status_code=500, detail="Failed to fetch market data")

    if not bars:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data found for {ticker} "
            f"between {start_date} and {end_date}",
        )

    # 2. Run every registered strategy
    results = []
    for strategy_type, strategy_cls in STRATEGY_REGISTRY.items():
        try:
            strategy = strategy_cls()
            config = BacktestConfig(
                ticker=ticker,
                strategy=strategy,
                start_date=start,
                end_date=end,
                initial_capital=initial_capital,
            )
            result = run_backtest(config, bars)

            sell_pnls = [t.pnl for t in result.trades if t.pnl != 0]
            gross_profit = sum(p for p in sell_pnls if p > 0)
            gross_loss = abs(sum(p for p in sell_pnls if p < 0))
            profit_factor = (
                gross_profit / gross_loss
                if gross_loss > 0
                else (999.0 if gross_profit > 0 else 0)
            )

            results.append(
                {
                    "strategy_name": strategy.name,
                    "strategy_type": strategy_type,
                    "winner": False,
                    "metrics": {
                        "total_return_pct": result.metrics.total_return_pct,
                        "sharpe_ratio": result.metrics.sharpe_ratio,
                        "max_drawdown_pct": result.metrics.max_drawdown_pct,
                        "win_rate": result.metrics.win_rate,
                        "total_trades": result.metrics.total_trades,
                        "profit_factor": profit_factor,
                        "final_value": result.metrics.final_value,
                    },
                }
            )
        except Exception:
            logger.exception("Strategy %s failed during comparison", strategy_type)

    # 3. Sort by total_return_pct descending and mark the winner
    results.sort(key=lambda r: r["metrics"]["total_return_pct"], reverse=True)
    if results:
        results[0]["winner"] = True

    return {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "results": results,
    }


@router.get("/results/{result_id}/export")
async def export_result(result_id: int, format: str = "csv", db: Session = Depends(get_db)):
    """Export a backtest result as CSV."""
    result = (
        db.query(BacktestResultModel)
        .filter(BacktestResultModel.id == result_id)
        .first()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")

    if format != "csv":
        raise HTTPException(status_code=400, detail="Only CSV export is supported")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Side", "Price", "Quantity", "Value", "PnL"])
    for t in result.trades:
        writer.writerow([str(t.date), t.side, t.price, t.quantity, t.value, t.pnl])

    output.seek(0)
    filename = f"backtest_{result_id}_{result.ticker}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Statistical significance
# ---------------------------------------------------------------------------
@router.post("/significance")
async def significance(req: BacktestRequest):
    """Run a backtest, then test whether its Sharpe is statistically real.

    Two outputs:
      * `bootstrap_ci`: 95% CI on Sharpe via i.i.d. bootstrap (n=2000)
      * `permutation`: one-sided p-value vs random shuffles of the same
        return distribution (n=2000)

    A bootstrap CI that comfortably excludes 0, *and* a permutation
    p-value < 0.05, together suggest the strategy is doing more than
    riding the underlying return distribution.
    """
    import numpy as np

    strategy_cls = STRATEGY_REGISTRY.get(req.strategy_type)
    if strategy_cls is None:
        raise HTTPException(status_code=400, detail=f"Unknown strategy '{req.strategy_type}'")

    bars = await provider.get_ohlcv(req.ticker, req.start_date, req.end_date)
    if not bars:
        raise HTTPException(status_code=400, detail=f"No OHLCV data for {req.ticker}")

    strategy = strategy_cls(req.params)
    config = BacktestConfig(
        ticker=req.ticker,
        strategy=strategy,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=req.initial_capital,
    )
    result = run_backtest(config, bars)

    equity = np.array([v for _, v in result.equity_curve], dtype=np.float64)
    rets = returns_from_equity(equity)
    if len(rets) < 5:
        raise HTTPException(status_code=400, detail="Backtest produced too few return observations")

    boot = bootstrap_sharpe_ci(rets)
    perm = permutation_test_sharpe(rets)

    return {
        "ticker": req.ticker,
        "strategy_type": req.strategy_type,
        "n_observations": int(len(rets)),
        "bootstrap_ci": {
            "point_estimate": boot.point_estimate,
            "ci_low": boot.ci_low,
            "ci_high": boot.ci_high,
            "confidence": boot.confidence,
            "n_resamples": boot.n_resamples,
        },
        "permutation": {
            "observed_sharpe": perm.observed_sharpe,
            "p_value": perm.p_value,
            "null_mean": perm.null_mean,
            "null_std": perm.null_std,
            "n_permutations": perm.n_permutations,
        },
        "interpretation": _interpret(boot, perm),
    }


def _interpret(boot, perm) -> str:
    sig = perm.p_value < 0.05
    pos = boot.ci_low > 0
    if sig and pos:
        return "Sharpe is positive with 95% confidence and significantly different from random shuffles (p<0.05). Signal is plausibly real."
    if sig and not pos:
        return "Significant per permutation test but bootstrap CI includes zero — interpret with caution."
    if pos and not sig:
        return "Bootstrap CI is positive but permutation p-value is not significant — Sharpe may reflect distributional luck."
    return "Insufficient evidence: CI includes zero and permutation p-value is not significant. Strategy is not distinguishable from chance on this sample."
