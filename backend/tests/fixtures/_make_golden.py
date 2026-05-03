"""One-shot script to capture golden backtest outputs from the CURRENT
implementation of `engine.backtest.run_backtest`. Re-run this only if the
intended behavior of the engine genuinely changes.

Usage:
    cd backend && ./venv/bin/python tests/fixtures/_make_golden.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import numpy as np

# Make the backend root importable regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from data.provider import OHLCVBar  # noqa: E402
from engine.backtest import BacktestConfig, run_backtest  # noqa: E402
from engine.strategy import STRATEGY_REGISTRY  # noqa: E402


# --------------------------------------------------------------------------- #
# Deterministic synthetic SPY-like OHLCV fixture (500 bars, seed=42)
# --------------------------------------------------------------------------- #
def make_synthetic_bars(n_bars: int = 500, seed: int = 42) -> list[OHLCVBar]:
    rng = np.random.default_rng(seed)
    # Geometric brownian motion with mild drift, ~1% daily vol, starting at 400.
    log_rets = rng.normal(loc=0.0003, scale=0.012, size=n_bars)
    closes = 400.0 * np.exp(np.cumsum(log_rets))

    # Fabricate OHLC around the close with deterministic intra-bar range.
    bar_ranges = rng.uniform(0.005, 0.025, size=n_bars)  # 0.5%..2.5%
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


def trade_to_dict(t) -> dict:
    return {
        "date": t.date.isoformat(),
        "side": t.side,
        "price": t.price,
        "quantity": t.quantity,
        "value": t.value,
        "commission": t.commission,
        "slippage_cost": t.slippage_cost,
        "pnl": t.pnl,
        "reason": t.reason,
    }


def result_to_dict(result) -> dict:
    return {
        "trades": [trade_to_dict(t) for t in result.trades],
        "equity_curve": [[d.isoformat(), v] for d, v in result.equity_curve],
        "metrics": {
            "total_return_pct": result.metrics.total_return_pct,
            "annualized_return_pct": result.metrics.annualized_return_pct,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "sortino_ratio": result.metrics.sortino_ratio,
            "calmar_ratio": result.metrics.calmar_ratio,
            "max_drawdown_pct": result.metrics.max_drawdown_pct,
            "max_drawdown_duration_bars": result.metrics.max_drawdown_duration_bars,
            "downside_deviation": result.metrics.downside_deviation,
        },
        "final_cash": (result.equity_curve[-1][1] if result.equity_curve else None),
        "n_trades": len(result.trades),
        "n_sells": sum(1 for t in result.trades if t.side == "sell"),
    }


# --------------------------------------------------------------------------- #
# Build the variants matrix
# --------------------------------------------------------------------------- #
VARIANTS = [
    # Plain runs (no risk overlays) for every strategy.
    {"name": "momentum_plain", "strategy": "momentum", "overlays": {}},
    {"name": "mean_reversion_plain", "strategy": "mean_reversion", "overlays": {}},
    {"name": "bollinger_bands_plain", "strategy": "bollinger_bands", "overlays": {}},
    {"name": "macd_plain", "strategy": "macd", "overlays": {}},
    {"name": "volume_momentum_plain", "strategy": "volume_momentum", "overlays": {}},
    # Combined risk overlays — exercises the trickiest path-dependent code.
    {
        "name": "momentum_overlays",
        "strategy": "momentum",
        "overlays": {
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "atr_stop_multiplier": 2.0,
        },
    },
    {
        "name": "mean_reversion_overlays",
        "strategy": "mean_reversion",
        "overlays": {
            "stop_loss_pct": 0.04,
            "take_profit_pct": 0.08,
        },
    },
    {
        "name": "macd_overlays",
        "strategy": "macd",
        "overlays": {
            "atr_stop_multiplier": 1.5,
        },
    },
]


def main() -> None:
    bars = make_synthetic_bars()
    out: dict = {
        "fixture": {
            "n_bars": len(bars),
            "seed": 42,
            "first_date": bars[0].date.isoformat(),
            "last_date": bars[-1].date.isoformat(),
            "first_close": bars[0].close,
            "last_close": bars[-1].close,
        },
        "config_defaults": {
            "initial_capital": 100_000.0,
            "commission_pct": 0.0,
            "commission_per_share": 0.0,
            "slippage_bps": 5.0,
            "position_size_pct": 0.95,
        },
        "results": {},
    }

    for v in VARIANTS:
        strat_cls = STRATEGY_REGISTRY[v["strategy"]]
        strategy = strat_cls()
        cfg = BacktestConfig(
            ticker="SYN",
            strategy=strategy,
            start_date=bars[0].date,
            end_date=bars[-1].date,
            initial_capital=100_000.0,
            commission_pct=0.0,
            commission_per_share=0.0,
            slippage_bps=5.0,
            position_size_pct=0.95,
            **v["overlays"],
        )
        result = run_backtest(cfg, bars)
        out["results"][v["name"]] = {
            "strategy": v["strategy"],
            "overlays": v["overlays"],
            **result_to_dict(result),
        }
        print(
            f"  {v['name']:30s}  trades={len(result.trades):3d}  "
            f"final_eq={result.equity_curve[-1][1]:,.4f}  "
            f"sharpe={result.metrics.sharpe_ratio:.4f}"
        )

    out_path = os.path.join(_HERE, "backtest_golden.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
