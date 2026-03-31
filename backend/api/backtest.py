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

    # Build response matching frontend expected shape
    return _format_result(db_result, req.strategy_type, result.equity_curve, result.metrics)


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
        avg_pnl = metrics_obj.avg_trade_pnl
        best_pnl = metrics_obj.best_trade_pnl
        worst_pnl = metrics_obj.worst_trade_pnl
        profit_factor = metrics_obj.profit_factor

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
        },
        "trades": trades,
        "equity_curve": [
            [str(d), v] for d, v in (equity_curve or [])
        ],
    }


@router.get("/results")
async def list_results(db: Session = Depends(get_db)):
    """List all saved backtest results."""
    results = db.query(BacktestResultModel).order_by(BacktestResultModel.created_at.desc()).all()
    return [_format_result(r) for r in results]


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
