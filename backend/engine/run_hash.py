"""Reproducibility hash for backtests.

Implements the QuantSense reproducibility contract: a 16-char hex prefix
of sha256 over a *canonical* serialization of (price_data, config,
code_version). Two runs that produce the same hash are guaranteed to
produce byte-identical equity curves, byte-identical bootstrap CIs (when
seeded from the hash), and byte-identical permutation p-values.

Design notes:

* Canonical JSON: `sort_keys=True`, no whitespace, keys cast to str.
  Means dict insertion order, set iteration order, etc. cannot leak
  into the digest.

* Price data is encoded as `[date_iso, open, high, low, close, volume]`
  tuples in the order received. Bars from yfinance/CSV are already
  date-sorted; we deliberately do NOT re-sort here so a caller passing
  out-of-order bars gets a different hash (it IS a different input).

* Strategy objects aren't dataclasses but their `params` dict and class
  name fully determine the deterministic strategy behavior, so we
  capture both in `_canonicalize`.

* `code_version` is captured ONCE at import time via `git rev-parse
  HEAD`; if not in a git repo or git is unavailable we fall back to
  `"dev"`. Capturing once (rather than on every call) keeps the hash
  stable for the lifetime of a process even if the working tree is
  modified mid-run.

We do NOT include a `seed` in the hash inputs — the API path *derives*
the seed from the hash so a single config request always yields the
same CI / p-value. Including the seed would make the relationship
circular.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import subprocess
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from data.provider import OHLCVBar

    from .backtest import BacktestConfig
    from .portfolio import PortfolioBacktestConfig

logger = logging.getLogger(__name__)


def _capture_code_version() -> str:
    """Capture the current git HEAD once at module import time.

    Falls back to ``"dev"`` if not inside a git repo or if `git` is not
    on PATH.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as exc:
        logger.debug("Could not capture code version via git: %s", exc)
    return "dev"


CODE_VERSION: str = _capture_code_version()


def _canonicalize(obj: Any) -> Any:
    """Convert an arbitrary Python value to a JSON-serializable, canonical form.

    Handles dataclasses, Strategy-like objects, dates, enums, and the
    usual primitives. The output is fed to `json.dumps(sort_keys=True)`
    so map-key ordering is irrelevant; we just need every value to be
    JSON-typed.
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return _canonicalize(obj.value)
    if isinstance(obj, dict):
        return {str(k): _canonicalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canonicalize(x) for x in obj]
    if isinstance(obj, (set, frozenset)):
        # Sets are unordered; canonicalize as a sorted list.
        return sorted(
            (_canonicalize(x) for x in obj), key=lambda v: json.dumps(v, sort_keys=True)
        )
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _canonicalize(dataclasses.asdict(obj))
    if hasattr(obj, "__dict__"):
        return {
            "__class__": type(obj).__name__,
            "fields": _canonicalize(
                {k: v for k, v in vars(obj).items() if not k.startswith("_")}
            ),
        }
    return str(obj)


def _bars_payload(price_data: list[OHLCVBar]) -> list[list[Any]]:
    """Encode OHLCV bars as ``[date_iso, open, high, low, close, volume]`` tuples.

    Floats are kept as-is (CSV/yfinance values round-trip exactly through
    JSON for the precision we use); volume is forced to int.
    """
    return [
        [
            b.date.isoformat(),
            float(b.open),
            float(b.high),
            float(b.low),
            float(b.close),
            int(b.volume),
        ]
        for b in price_data
    ]


def compute_run_hash(
    price_data: list[OHLCVBar] | Mapping[str, list[OHLCVBar]],
    config: BacktestConfig | PortfolioBacktestConfig,
    code_version: str | None = None,
) -> str:
    """Compute a 16-char hex sha256 prefix over canonical(price_data + config + code_version).

    Args:
        price_data: OHLCV bars exactly as they will be fed to
            ``run_backtest`` (single-asset list) OR a ``{ticker: bars}``
            mapping for the multi-asset portfolio path. For the mapping
            shape, tickers are encoded in sorted order so dict
            insertion-order leaks cannot affect the digest.
        config: the ``BacktestConfig`` or ``PortfolioBacktestConfig``.
            Both are dataclasses; ``_canonicalize`` walks them
            recursively (including the nested strategy / weights dicts).
        code_version: override for testing. ``None`` uses the module-level
            ``CODE_VERSION`` captured at import time from ``git rev-parse
            HEAD`` (or ``"dev"`` if not in a git repo).

    Returns:
        First 16 hex chars of sha256(canonical_json). 64 bits of entropy
        is plenty to make accidental collisions a non-event for
        backtests.
    """
    if isinstance(price_data, Mapping):
        bars_canonical: Any = {
            str(ticker): _bars_payload(bars)
            for ticker, bars in sorted(price_data.items(), key=lambda kv: str(kv[0]))
        }
    else:
        bars_canonical = _bars_payload(price_data)
    payload = {
        "price_data": bars_canonical,
        "config": _canonicalize(config),
        "code_version": code_version if code_version is not None else CODE_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:16]


def seed_from_run_hash(run_hash: str) -> int:
    """Derive a deterministic 32-bit seed from a run hash.

    The bootstrap / permutation API path uses this so the same backtest
    config always yields the same CI bounds and p-value — the seed is a
    pure function of (price_data, config, code_version).
    """
    return int(run_hash[:8], 16)
