"""Backtest endpoints – run, list, and inspect backtests."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from data.yahoo_provider import YahooFinanceProvider
from engine.backtest import BacktestConfig, run_backtest
from engine.strategy import STRATEGY_REGISTRY
from models.database import get_db
from models.pydantic_models import (
    BacktestRequest,
    BacktestResponse,
    BacktestTradeResponse,
)
from models.schemas import BacktestResult as BacktestResultModel
from models.schemas import BacktestTrade as BacktestTradeModel
from models.schemas import Strategy as StrategyModel

router = APIRouter()
provider = YahooFinanceProvider()
logger = logging.getLogger(__name__)


@router.post("/run", response_model=BacktestResponse)
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

    # 5. Save backtest result
    db_result = BacktestResultModel(
        strategy_id=db_strategy.id,
        ticker=req.ticker,
        start_date=req.start_date,
        end_date=req.end_date,
        initial_capital=result.metrics.initial_capital,
        final_value=result.metrics.final_value,
        total_return_pct=result.metrics.total_return_pct,
        sharpe_ratio=result.metrics.sharpe_ratio,
        max_drawdown_pct=result.metrics.max_drawdown_pct,
        win_rate=result.metrics.win_rate,
        total_trades=result.metrics.total_trades,
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

    return db_result


@router.get("/results", response_model=list[BacktestResponse])
async def list_results(db: Session = Depends(get_db)):
    """List all saved backtest results."""
    results = db.query(BacktestResultModel).order_by(BacktestResultModel.created_at.desc()).all()
    return results


@router.get("/results/{result_id}", response_model=BacktestResponse)
async def get_result(result_id: int, db: Session = Depends(get_db)):
    """Get a specific backtest result with its trades."""
    result = db.query(BacktestResultModel).filter(BacktestResultModel.id == result_id).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return result


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
