"""Tests for the multi-asset portfolio backtester (engine.portfolio)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from data.provider import OHLCVBar
from engine.portfolio import (
    PortfolioBacktestConfig,
    run_portfolio_backtest,
)
from engine.run_hash import compute_run_hash


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _bar(d: date, o: float, c: float | None = None) -> OHLCVBar:
    """Build a synthetic bar with high=max(o,c)*1.0 and low=min(o,c)*1.0."""
    if c is None:
        c = o
    return OHLCVBar(
        date=d,
        open=float(o),
        high=float(max(o, c)),
        low=float(min(o, c)),
        close=float(c),
        volume=1_000_000,
    )


def _make_pair(
    dates: list[date],
    a_prices: list[tuple[float, float]],
    b_prices: list[tuple[float, float]],
) -> dict[str, list[OHLCVBar]]:
    assert len(dates) == len(a_prices) == len(b_prices)
    a_bars = [_bar(d, o, c) for d, (o, c) in zip(dates, a_prices, strict=False)]
    b_bars = [_bar(d, o, c) for d, (o, c) in zip(dates, b_prices, strict=False)]
    return {"A": a_bars, "B": b_bars}


# --------------------------------------------------------------------------- #
# 1. 2-asset equal-weight, no rebalance, deterministic synthetic data
# --------------------------------------------------------------------------- #
def test_two_asset_equal_weight_never_rebalance_hand_computed():
    """Initial trigger at bar 0, executes at bar 1 OPEN; hold to end.

    Bar 1 open=100/50 -> buy 5 A and 10 B with $1000 (zero costs).
    Bar 2 close=110/55 -> equity = 5*110 + 10*55 = 1100. (+10%)
    """
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    bars = _make_pair(
        dates,
        a_prices=[(100, 100), (100, 100), (110, 110)],
        b_prices=[(50, 50), (50, 50), (55, 55)],
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights=None,  # equal-weight
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="never",
        slippage_bps=0.0,
        commission_per_share=0.0,
        commission_pct=0.0,
        benchmark_ticker=None,
    )
    result = run_portfolio_backtest(cfg, bars)

    assert result.equity_curve[0] == pytest.approx(1000.0)  # all cash pre-exec
    assert result.equity_curve[1] == pytest.approx(1000.0)  # post-exec MTM
    assert result.equity_curve[-1] == pytest.approx(1100.0)
    assert result.final_positions == pytest.approx({"A": 5.0, "B": 10.0})
    assert result.final_cash == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 2. 2-asset equal-weight, monthly rebalance, drift correction
# --------------------------------------------------------------------------- #
def test_monthly_rebalance_corrects_drift_back_to_equal_weight():
    """A doubles from 100 -> 200 in Jan; B flat at 50.

    After rebalance at start of Feb, weights snap back to ~50/50.
    """
    dates = [
        date(2024, 1, 30),  # bar 0 — initial trigger
        date(2024, 1, 31),  # bar 1 — initial exec @ open=100/50; close shows 200/50
        date(2024, 2, 1),  # bar 2 — month rollover -> trigger
        date(2024, 2, 2),  # bar 3 — rebalance exec @ open=200/50
    ]
    bars = _make_pair(
        dates,
        a_prices=[(100, 100), (100, 200), (200, 200), (200, 200)],
        b_prices=[(50, 50), (50, 50), (50, 50), (50, 50)],
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.5, "B": 0.5},
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="monthly",
        slippage_bps=0.0,
        commission_per_share=0.0,
        commission_pct=0.0,
        benchmark_ticker=None,
    )
    result = run_portfolio_backtest(cfg, bars)

    # After initial buy at bar 1: 5 A @ 100, 10 B @ 50.
    # Bar 1 close MTM: 5*200 + 10*50 = 1500.
    assert result.equity_curve[1] == pytest.approx(1500.0)
    # Bar 2 close: still 1500 (no rebalance yet, prices flat).
    assert result.equity_curve[2] == pytest.approx(1500.0)

    # After rebalance on bar 3 open: target = 750 each. qty_A = 750/200 = 3.75,
    # qty_B = 750/50 = 15. Cash unchanged (sells 1.25 A @ 200 = 250; buys 5 B @ 50 = 250).
    assert result.final_positions["A"] == pytest.approx(3.75)
    assert result.final_positions["B"] == pytest.approx(15.0)

    # Post-rebalance weights at bar 3 close should be ~50/50.
    final_eq = result.equity_curve[-1]
    w_a = result.final_positions["A"] * 200 / final_eq
    w_b = result.final_positions["B"] * 50 / final_eq
    assert w_a == pytest.approx(0.5, abs=1e-9)
    assert w_b == pytest.approx(0.5, abs=1e-9)


# --------------------------------------------------------------------------- #
# 3. Turnover tracked correctly
# --------------------------------------------------------------------------- #
def test_total_turnover_matches_hand_computation():
    """For the drift-correction case (test 2), hand-compute total turnover.

    Initial buys at bar 1 open: 5 A * 100 + 10 B * 50 = $1000.
    Rebalance sells/buys at bar 3 open: 1.25 A * 200 + 5 B * 50 = $500.
    Total turnover = $1500 (notional $ of all trades).
    """
    dates = [
        date(2024, 1, 30),
        date(2024, 1, 31),
        date(2024, 2, 1),
        date(2024, 2, 2),
    ]
    bars = _make_pair(
        dates,
        a_prices=[(100, 100), (100, 200), (200, 200), (200, 200)],
        b_prices=[(50, 50), (50, 50), (50, 50), (50, 50)],
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.5, "B": 0.5},
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="monthly",
        slippage_bps=0.0,
        commission_per_share=0.0,
        commission_pct=0.0,
        benchmark_ticker=None,
    )
    result = run_portfolio_backtest(cfg, bars)
    assert result.total_turnover == pytest.approx(1500.0)


# --------------------------------------------------------------------------- #
# 4. Per-leg commissions applied
# --------------------------------------------------------------------------- #
def test_per_leg_commissions_reduce_final_equity_by_exact_amount():
    """commission_per_share=$0.01, no slippage, no rebalance.

    Initial buy: 5 A + 10 B at bar 1 open (100/50). Commission = (5+10)*0.01 = $0.15.
    Final equity = 1000 - 0.15 = $999.85 (since prices don't move in this case).
    """
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    bars = _make_pair(
        dates,
        a_prices=[(100, 100), (100, 100)],
        b_prices=[(50, 50), (50, 50)],
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.5, "B": 0.5},
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="never",
        slippage_bps=0.0,
        commission_per_share=0.01,
        commission_pct=0.0,
        benchmark_ticker=None,
    )
    result = run_portfolio_backtest(cfg, bars)

    total_commissions = sum(
        f.commission for legs in result.fills.values() for f in legs
    )
    assert total_commissions == pytest.approx(0.15)
    assert result.equity_curve[-1] == pytest.approx(1000.0 - 0.15)


# --------------------------------------------------------------------------- #
# 5. Per-leg slippage applied — buys and sells
# --------------------------------------------------------------------------- #
def test_per_leg_slippage_applies_to_buys_and_sells():
    """slippage_bps=10 -> 0.001 (10 bps).

    Buys (initial allocation, bar 1 open=100/50):
      A fill = 100 * 1.001 = 100.1
      B fill = 50  * 1.001 =  50.05
    Sell (rebalance at bar 3 open=200/50):
      A fill = 200 * 0.999 = 199.8
    Buy (rebalance at bar 3 open=50):
      B fill =  50 * 1.001 =  50.05
    """
    dates = [
        date(2024, 1, 30),
        date(2024, 1, 31),
        date(2024, 2, 1),
        date(2024, 2, 2),
    ]
    bars = _make_pair(
        dates,
        a_prices=[(100, 100), (100, 200), (200, 200), (200, 200)],
        b_prices=[(50, 50), (50, 50), (50, 50), (50, 50)],
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.5, "B": 0.5},
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="monthly",
        slippage_bps=10.0,
        commission_per_share=0.0,
        commission_pct=0.0,
        benchmark_ticker=None,
    )
    result = run_portfolio_backtest(cfg, bars)

    a_fills = result.fills["A"]
    b_fills = result.fills["B"]

    assert a_fills[0].side == "buy"
    assert a_fills[0].fill_price == pytest.approx(100.0 * 1.001)
    assert b_fills[0].side == "buy"
    assert b_fills[0].fill_price == pytest.approx(50.0 * 1.001)

    # Rebalance leg: A is a sell, B is a buy.
    assert a_fills[1].side == "sell"
    assert a_fills[1].fill_price == pytest.approx(200.0 * 0.999)
    assert b_fills[1].side == "buy"
    assert b_fills[1].fill_price == pytest.approx(50.0 * 1.001)


# --------------------------------------------------------------------------- #
# 6. Reproducibility
# --------------------------------------------------------------------------- #
def test_same_config_same_data_yields_byte_identical_results():
    """Reproducibility contract: identical inputs -> same hash + equity curve."""
    rng = np.random.default_rng(123)
    n = 80
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n)]
    a_path = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    b_path = 80 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    bars = {
        "A": [_bar(d, p, p) for d, p in zip(dates, a_path, strict=False)],
        "B": [_bar(d, p, p) for d, p in zip(dates, b_path, strict=False)],
    }
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.6, "B": 0.4},
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=10_000.0,
        rebalance_schedule="monthly",
        slippage_bps=5.0,
        commission_per_share=0.005,
        commission_pct=0.0001,
        benchmark_ticker=None,
    )
    r1 = run_portfolio_backtest(cfg, bars)
    r2 = run_portfolio_backtest(cfg, bars)

    assert r1.run_hash == r2.run_hash
    assert np.array_equal(r1.equity_curve, r2.equity_curve)
    assert r1.final_cash == r2.final_cash
    assert r1.final_positions == r2.final_positions
    assert r1.total_turnover == r2.total_turnover

    # And the run_hash matches a direct compute_run_hash call.
    assert r1.run_hash == compute_run_hash(bars, cfg, code_version=None)


# --------------------------------------------------------------------------- #
# 7. Empty-data handling
# --------------------------------------------------------------------------- #
def test_empty_ticker_data_raises_value_error():
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
    bars = _make_pair(
        dates,
        a_prices=[(100, 100), (100, 100), (110, 110)],
        b_prices=[(50, 50), (50, 50), (55, 55)],
    )
    bars["B"] = []  # wipe one leg
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights=None,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="never",
        benchmark_ticker=None,
    )
    with pytest.raises(ValueError, match="no bars"):
        run_portfolio_backtest(cfg, bars)


def test_missing_ticker_data_raises_value_error():
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    bars = {"A": [_bar(d, 100) for d in dates]}
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights=None,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="never",
        benchmark_ticker=None,
    )
    with pytest.raises(ValueError, match="No bar series"):
        run_portfolio_backtest(cfg, bars)


# --------------------------------------------------------------------------- #
# 8. Weights validation
# --------------------------------------------------------------------------- #
def test_weights_must_sum_to_one():
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    bars = _make_pair(
        dates, a_prices=[(100, 100), (100, 100)], b_prices=[(50, 50), (50, 50)]
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.4, "B": 0.4},  # sums to 0.8
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="never",
        benchmark_ticker=None,
    )
    with pytest.raises(ValueError, match="must sum to 1.0"):
        run_portfolio_backtest(cfg, bars)


def test_weight_on_unknown_ticker_raises():
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    bars = _make_pair(
        dates, a_prices=[(100, 100), (100, 100)], b_prices=[(50, 50), (50, 50)]
    )
    cfg = PortfolioBacktestConfig(
        tickers=["A", "B"],
        weights={"A": 0.5, "B": 0.3, "C": 0.2},
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        rebalance_schedule="never",
        benchmark_ticker=None,
    )
    with pytest.raises(ValueError, match="not in config.tickers"):
        run_portfolio_backtest(cfg, bars)
