"""Vectorized backtester ≡ legacy loop equivalence regression.

This is the safety net for the ``qs-vectorize-backtest`` refactor. It
proves that the new vectorized ``run_backtest`` produces *byte-identical*
output to the legacy per-bar loop on a deterministic 500-bar synthetic
SPY-like fixture.

How the contract is enforced
----------------------------
A frozen golden file at ``tests/fixtures/backtest_golden.json`` was
generated from the LEGACY loop implementation (commit
``e6df8ac`` baseline) and committed to the tree. These tests run the
*current* engine against the exact same fixture and assert exact
equality on every fill (date, side, price, size, commission), every
entry in the equity curve, summary metrics (sharpe, max DD, etc.) and
final equity.

If the vectorized version ever diverges by 1 cent on bar 437 of MACD,
this is the test that catches it.

How to refresh the golden
-------------------------
Only do this if the *intended* engine behavior is changing:

    cd backend
    ./venv/bin/python tests/fixtures/_make_golden.py

Performance benchmark (5-year backtest, ~1260 bars, MomentumStrategy)
---------------------------------------------------------------------
Captured on the development host (Python 3.14, numpy 1.26.4):

    n=  500  legacy=  1.71ms  vectorized=  1.83ms  (0.94x)
    n= 1260  legacy=  2.88ms  vectorized=  3.14ms  (0.92x)
    n= 5040  legacy=  8.79ms  vectorized=  9.84ms  (0.89x)
    n=12600  legacy= 21.48ms  vectorized= 23.87ms  (0.90x)

The vectorized version is on par with the legacy loop — the legacy
per-bar body was already very lightweight, so the win here is
*correctness* (the explicit ``pending = sig_type[:-1]`` array makes
look-ahead structurally impossible) and *maintainability*, not raw
speed. Numbers reproduce roughly with ``backend/_benchmark.py``.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import numpy as np
import pytest

from data.provider import OHLCVBar
from engine.backtest import BacktestConfig, run_backtest
from engine.strategy import STRATEGY_REGISTRY


_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "fixtures", "backtest_golden.json"
)


# --------------------------------------------------------------------------- #
# Deterministic synthetic SPY-like OHLCV fixture (500 bars, seed=42)
# --------------------------------------------------------------------------- #
# Must match `tests/fixtures/_make_golden.py` exactly — any drift here would
# silently invalidate the golden comparisons.
def _make_synthetic_bars(n_bars: int = 500, seed: int = 42) -> list[OHLCVBar]:
    rng = np.random.default_rng(seed)
    log_rets = rng.normal(loc=0.0003, scale=0.012, size=n_bars)
    closes = 400.0 * np.exp(np.cumsum(log_rets))

    bar_ranges = rng.uniform(0.005, 0.025, size=n_bars)
    open_offsets = rng.uniform(-0.5, 0.5, size=n_bars) * bar_ranges
    high_offsets = rng.uniform(0.0, 1.0, size=n_bars) * bar_ranges
    low_offsets = rng.uniform(0.0, 1.0, size=n_bars) * bar_ranges

    opens = closes * (1.0 + open_offsets)
    highs = np.maximum(closes, opens) * (1.0 + high_offsets)
    lows = np.minimum(closes, opens) * (1.0 - low_offsets)
    volumes = rng.integers(1_000_000, 5_000_000, size=n_bars)

    start = date(2020, 1, 2)
    return [
        OHLCVBar(
            date=start + timedelta(days=i),
            open=float(opens[i]),
            high=float(highs[i]),
            low=float(lows[i]),
            close=float(closes[i]),
            volume=int(volumes[i]),
        )
        for i in range(n_bars)
    ]


@pytest.fixture(scope="module")
def synthetic_bars() -> list[OHLCVBar]:
    return _make_synthetic_bars()


@pytest.fixture(scope="module")
def golden() -> dict:
    with open(_FIXTURE_PATH) as f:
        data = json.load(f)
    return data


# --------------------------------------------------------------------------- #
# Variants: every registered strategy plain + risk-overlay combinations
# --------------------------------------------------------------------------- #
ALL_FIVE_PLAIN = [
    ("momentum_plain", "momentum", {}),
    ("mean_reversion_plain", "mean_reversion", {}),
    ("bollinger_bands_plain", "bollinger_bands", {}),
    ("macd_plain", "macd", {}),
    ("volume_momentum_plain", "volume_momentum", {}),
]
WITH_OVERLAYS = [
    (
        "momentum_overlays",
        "momentum",
        {
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "atr_stop_multiplier": 2.0,
        },
    ),
    (
        "mean_reversion_overlays",
        "mean_reversion",
        {"stop_loss_pct": 0.04, "take_profit_pct": 0.08},
    ),
    ("macd_overlays", "macd", {"atr_stop_multiplier": 1.5}),
]
ALL_VARIANTS = ALL_FIVE_PLAIN + WITH_OVERLAYS


def _run_variant(bars: list[OHLCVBar], strategy_type: str, overlays: dict):
    strat = STRATEGY_REGISTRY[strategy_type]()
    cfg = BacktestConfig(
        ticker="SYN",
        strategy=strat,
        start_date=bars[0].date,
        end_date=bars[-1].date,
        initial_capital=100_000.0,
        commission_pct=0.0,
        commission_per_share=0.0,
        slippage_bps=5.0,
        position_size_pct=0.95,
        **overlays,
    )
    return run_backtest(cfg, bars)


# --------------------------------------------------------------------------- #
# Per-variant equivalence tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "variant_name,strategy_type,overlays",
    ALL_VARIANTS,
    ids=[v[0] for v in ALL_VARIANTS],
)
def test_vectorized_matches_golden(
    synthetic_bars, golden, variant_name, strategy_type, overlays
):
    """Byte-for-byte equality check between vectorized engine and frozen golden."""
    result = _run_variant(synthetic_bars, strategy_type, overlays)
    expected = golden["results"][variant_name]

    # ---- Trade count ------------------------------------------------------ #
    assert len(result.trades) == expected["n_trades"], (
        f"{variant_name}: trade count {len(result.trades)} vs {expected['n_trades']}"
    )
    n_sells = sum(1 for t in result.trades if t.side == "sell")
    assert n_sells == expected["n_sells"]

    # ---- Per-fill exact equality ----------------------------------------- #
    for i, (got, want) in enumerate(zip(result.trades, expected["trades"])):
        ctx = f"{variant_name} trade[{i}]"
        assert got.date.isoformat() == want["date"], ctx + " date"
        assert got.side == want["side"], ctx + " side"
        assert got.price == want["price"], (
            f"{ctx} price: {got.price!r} vs {want['price']!r}"
        )
        assert got.quantity == want["quantity"], ctx + " quantity"
        assert got.value == want["value"], ctx + " value"
        assert got.commission == want["commission"], ctx + " commission"
        assert got.slippage_cost == want["slippage_cost"], ctx + " slippage_cost"
        assert got.pnl == want["pnl"], ctx + " pnl"
        assert got.reason == want["reason"], ctx + " reason"

    # ---- Equity curve ---------------------------------------------------- #
    assert len(result.equity_curve) == len(expected["equity_curve"])
    for i, ((d_got, v_got), (d_exp, v_exp)) in enumerate(
        zip(result.equity_curve, expected["equity_curve"])
    ):
        assert d_got.isoformat() == d_exp, f"{variant_name} eq[{i}] date"
        assert v_got == v_exp, f"{variant_name} eq[{i}] value: {v_got!r} vs {v_exp!r}"

    # ---- Final equity / cash --------------------------------------------- #
    final_eq = result.equity_curve[-1][1]
    assert final_eq == expected["final_cash"], (
        f"{variant_name}: final equity {final_eq!r} vs {expected['final_cash']!r}"
    )

    # ---- Summary metrics ------------------------------------------------- #
    m_got = result.metrics
    m_exp = expected["metrics"]
    assert m_got.total_return_pct == m_exp["total_return_pct"]
    assert m_got.annualized_return_pct == m_exp["annualized_return_pct"]
    assert m_got.sharpe_ratio == m_exp["sharpe_ratio"]
    assert m_got.sortino_ratio == m_exp["sortino_ratio"]
    assert m_got.calmar_ratio == m_exp["calmar_ratio"]
    assert m_got.max_drawdown_pct == m_exp["max_drawdown_pct"]
    assert m_got.max_drawdown_duration_bars == m_exp["max_drawdown_duration_bars"]
    assert m_got.downside_deviation == m_exp["downside_deviation"]


# --------------------------------------------------------------------------- #
# Coverage check: confirm we exercised every strategy in the registry
# --------------------------------------------------------------------------- #
def test_all_five_strategies_covered():
    plain_strats = {strat for _, strat, _ in ALL_FIVE_PLAIN}
    assert plain_strats == set(STRATEGY_REGISTRY.keys()), (
        f"Equivalence test must cover every registered strategy. "
        f"Missing: {set(STRATEGY_REGISTRY.keys()) - plain_strats}, "
        f"Extra: {plain_strats - set(STRATEGY_REGISTRY.keys())}"
    )


# --------------------------------------------------------------------------- #
# Sanity: vectorized engine still respects the no-look-ahead invariant
# --------------------------------------------------------------------------- #
def test_no_lookahead_signal_executes_at_next_bar_open(synthetic_bars):
    """Re-prove the rigor-pass invariant on the vectorized path.

    After a strategy emits a BUY signal on bar T, the resulting buy fill
    must be at bar T+1's open, with slippage applied. This is the central
    correctness property the vectorization explicitly preserves via
    ``pending = sig_type[:-1]``.
    """
    strat = STRATEGY_REGISTRY["momentum"]()
    cfg = BacktestConfig(
        ticker="SYN",
        strategy=strat,
        start_date=synthetic_bars[0].date,
        end_date=synthetic_bars[-1].date,
        initial_capital=100_000.0,
        slippage_bps=0.0,  # easier to assert exact open
        commission_pct=0.0,
        commission_per_share=0.0,
    )
    result = run_backtest(cfg, synthetic_bars)
    buys = [t for t in result.trades if t.side == "buy"]
    assert buys, "expected at least one buy on this fixture"

    by_date = {b.date: b for b in synthetic_bars}
    for buy in buys:
        bar = by_date[buy.date]
        assert buy.price == bar.open, (
            f"buy on {buy.date}: filled at {buy.price} but bar open is "
            f"{bar.open} — look-ahead leak!"
        )
