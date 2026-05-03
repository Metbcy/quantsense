"""Fama-French factor risk decomposition for strategy returns.

The Fama-French factors are the standard "common risk premia" that explain
most of the cross-section of equity returns. The 3-factor model (Fama &
French, 1993) adds size (SMB, "small minus big") and value (HML, "high
minus low" book-to-market) on top of the market excess return (Mkt-RF).
The 5-factor extension (Fama & French, 2015) adds profitability (RMW,
"robust minus weak") and investment (CMA, "conservative minus
aggressive"). Carhart's 4-factor model (Carhart, 1997) augments the
3-factor model with a momentum factor (Mom / UMD, "up minus down"). All
factors are excess-return long/short portfolios published daily by Ken
French's data library.

Why this matters: a strategy with a great Sharpe might just be loaded on
SMB (i.e. systematically holding small-cap names) — that's a known risk
premium, not skill. Regressing strategy excess returns on the factors and
reading the *intercept* gives you "alpha after controlling for known
risk premia". A quant interview reviewer expects that exact framing: the
unconditional Sharpe is necessary but not sufficient, the factor-adjusted
alpha is the closer thing to evidence of edge.

How to read the result: a large t-stat (|t| > 2) on the **alpha**
intercept is the signal that there's return left over after subtracting
factor exposure — i.e. real alpha. A large t-stat on a factor coefficient
means the strategy has meaningful exposure to that factor (intentional or
unintentional); the sign tells you the direction. R² tells you what
fraction of the strategy's daily-return variance the factor model
explains; high R² + low alpha-t means the strategy is essentially a
factor sleeve in disguise. Alpha is annualized (× 252) and expressed in
percent, matching :func:`engine.metrics.compute_alpha_beta`. OLS is
deterministic so for a fixed strategy-return series and a fixed factor
cache the output is reproducible to floating-point precision.
"""

from __future__ import annotations

import io
import logging
import os
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import statsmodels.api as sm

logger = logging.getLogger(__name__)

TRADING_DAYS = 252

FactorModel = Literal["ff3", "ff5", "carhart4"]

# Kenneth French data library: dataset name -> (zip URL, expected csv member factor columns)
# The CSVs use percent-per-day for factor returns and RF, so divide by 100
# before regression.
_KF_BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
_KF_DATASETS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ff3": (
        f"{_KF_BASE}/F-F_Research_Data_Factors_daily_CSV.zip",
        ("Mkt-RF", "SMB", "HML", "RF"),
    ),
    "ff5": (
        f"{_KF_BASE}/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"),
    ),
    "mom": (
        f"{_KF_BASE}/F-F_Momentum_Factor_daily_CSV.zip",
        ("Mom",),
    ),
}

# Factor columns required for each model (excluding RF which is handled
# separately for the excess-return transformation).
_MODEL_FACTORS: dict[FactorModel, tuple[str, ...]] = {
    "ff3": ("Mkt-RF", "SMB", "HML"),
    "ff5": ("Mkt-RF", "SMB", "HML", "RMW", "CMA"),
    "carhart4": ("Mkt-RF", "SMB", "HML", "Mom"),
}


@dataclass
class FactorLoading:
    """OLS regression diagnostics for one factor."""

    coefficient: float
    se: float
    t_stat: float
    pvalue: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FactorExposure:
    """Result of regressing strategy (excess) returns on a factor model.

    Alpha is annualized (× 252) and expressed in percent — same convention
    as :class:`engine.metrics.AlphaBetaResult`. Factor coefficients are
    unitless (slope of strategy daily return on factor daily return).
    Standard errors come from a heteroskedasticity-robust HC1 covariance
    matrix (statsmodels ``cov_type='HC1'``).
    """

    model: FactorModel
    alpha: float
    alpha_se: float
    alpha_t: float
    alpha_pvalue: float
    factors: dict[str, FactorLoading] = field(default_factory=dict)
    r_squared: float = 0.0
    adj_r_squared: float = 0.0
    n_obs: int = 0
    start_date: date | None = None
    end_date: date | None = None
    risk_free_subtracted: bool = True

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "alpha": self.alpha,
            "alpha_se": self.alpha_se,
            "alpha_t": self.alpha_t,
            "alpha_pvalue": self.alpha_pvalue,
            "factors": {k: v.to_dict() for k, v in self.factors.items()},
            "r_squared": self.r_squared,
            "adj_r_squared": self.adj_r_squared,
            "n_obs": self.n_obs,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "risk_free_subtracted": self.risk_free_subtracted,
        }


# ---------------------------------------------------------------------------
# Cache helper
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    """Return the configured factor-cache directory (created if missing).

    Honours ``QUANTSENSE_FACTOR_CACHE_DIR`` env var (used in tests to
    isolate per-test caches); falls back to ``~/.quantsense/cache``.
    """
    override = os.environ.get("QUANTSENSE_FACTOR_CACHE_DIR")
    base = Path(override) if override else Path.home() / ".quantsense" / "cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cache_path(model: FactorModel) -> Path:
    return _cache_dir() / f"factors_{model}.parquet"


def _parse_kf_csv(text: str, columns: tuple[str, ...]) -> pd.DataFrame:
    """Parse a Kenneth French daily factor CSV into a tidy DataFrame.

    The KF CSVs have a multi-line header preamble, then a header row
    starting with "," then YYYYMMDD,col,col,...; daily data ends and a
    second annual block sometimes follows after a blank line. We keep
    only the daily block.

    Returns a DataFrame indexed by ``date`` with the named columns,
    *still in percent units* (raw KF). Conversion to fractions is done
    at regression time.
    """
    lines = text.splitlines()
    # Find the header row: first line that, when split on commas, has the
    # expected factor columns (in some order, leading empty cell for date).
    header_idx = None
    for i, ln in enumerate(lines):
        parts = [p.strip() for p in ln.split(",")]
        if not parts or parts[0] != "":
            continue
        cols = parts[1:]
        if all(c in cols for c in columns):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(
            f"could not locate header with columns {columns} in KF CSV "
            f"(first 5 lines: {lines[:5]!r})"
        )

    header_cols = [p.strip() for p in lines[header_idx].split(",")][1:]
    data_rows: list[list[str]] = []
    for ln in lines[header_idx + 1 :]:
        ln = ln.strip()
        if not ln:
            # blank line ends the daily block (annual block follows in some files)
            break
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) != len(header_cols) + 1:
            break
        # First field must look like YYYYMMDD; bail when annual format (YYYY) appears
        if not (parts[0].isdigit() and len(parts[0]) == 8):
            break
        data_rows.append(parts)

    if not data_rows:
        raise ValueError("no daily rows parsed from KF CSV")

    df = pd.DataFrame(data_rows, columns=["date", *header_cols])
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
    for c in header_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=list(columns))
    df = df.set_index("date").sort_index()
    return df[list(columns)]


def _http_fetch_kf_zip(url: str, *, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "QuantSense/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        members = zf.namelist()
        if not members:
            raise ValueError(f"empty zip at {url}")
        return zf.read(members[0]).decode("latin-1")


def _fetch_kf_dataset(dataset_key: str) -> pd.DataFrame:
    """Fetch and parse one Kenneth French dataset by key (``ff3``/``ff5``/``mom``).

    Tries ``pandas_datareader.famafrench.FamaFrenchReader`` first when the
    package is installed and importable; otherwise falls back to a direct
    HTTPS download from the Kenneth French data library (which is exactly
    what pdr does internally). Network access is required when the cache
    is cold; tests should mock this function.

    Note: ``pandas-datareader`` is intentionally NOT pinned in
    ``requirements.txt`` — it currently has a hard incompatibility with
    pandas 3.x (it calls ``pd.util._decorators.deprecate_kwarg`` with the
    old positional API and crashes on import). The direct-HTTP path
    fetches the same files from the same source, so the fallback is a
    full substitute, not a degraded path.
    """
    url, columns = _KF_DATASETS[dataset_key]

    try:
        from pandas_datareader.famafrench import FamaFrenchReader  # type: ignore

        ds_name = {
            "ff3": "F-F_Research_Data_Factors_daily",
            "ff5": "F-F_Research_Data_5_Factors_2x3_daily",
            "mom": "F-F_Momentum_Factor_daily",
        }[dataset_key]
        reader = FamaFrenchReader(ds_name, start="1926-01-01")
        data = reader.read()
        reader.close()
        df = data[0].copy()
        df.columns = [c.strip() for c in df.columns]
        df.index = pd.to_datetime(df.index).date
        df.index.name = "date"
        return df[[c for c in columns if c in df.columns]]
    except Exception as exc:  # pragma: no cover - exercised when pdr is healthy
        logger.info("pandas-datareader path unavailable (%s); using direct HTTP", exc)

    text = _http_fetch_kf_zip(url)
    return _parse_kf_csv(text, columns)


def _read_cache(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        logger.warning("factor cache at %s unreadable; ignoring", path)
        return None
    # The 'date' column was written from a python date index; restore it.
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.set_index("date")
    df = df.sort_index()
    return df


def _write_cache(path: Path, df: pd.DataFrame) -> None:
    out = df.copy()
    out.index = pd.to_datetime(out.index)
    out.index.name = "date"
    out = out.reset_index()
    # Parquet date32 → use string roundtrip via datetime to keep schema simple.
    out["date"] = out["date"].dt.date.astype(str)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)


def _load_or_fetch_factors(model: FactorModel, start: date, end: date) -> pd.DataFrame:
    """Load FF factors for ``model`` covering ``[start, end]``.

    Cache schema (Parquet at ``~/.quantsense/cache/factors_<model>.parquet``):

    +-----------+----------+------------------------------------------+
    | column    | dtype    | meaning                                  |
    +===========+==========+==========================================+
    | date      | string   | trading day, ISO ``YYYY-MM-DD``          |
    +-----------+----------+------------------------------------------+
    | Mkt-RF    | float64  | market excess return, percent / day      |
    +-----------+----------+------------------------------------------+
    | SMB       | float64  | size factor, percent / day               |
    +-----------+----------+------------------------------------------+
    | HML       | float64  | value factor, percent / day              |
    +-----------+----------+------------------------------------------+
    | RMW       | float64  | profitability (ff5 only), percent / day  |
    +-----------+----------+------------------------------------------+
    | CMA       | float64  | investment (ff5 only), percent / day     |
    +-----------+----------+------------------------------------------+
    | Mom       | float64  | momentum (carhart4 only), percent / day  |
    +-----------+----------+------------------------------------------+
    | RF        | float64  | risk-free rate, percent / day            |
    +-----------+----------+------------------------------------------+

    Values are stored in the original Kenneth French units (percent per
    day) and converted to fractions inside :func:`compute_factor_exposure`
    before regression. The on-disk file is always the *full* fetched
    history; partial coverage of the requested ``[start, end]`` window
    triggers a refresh.
    """
    if start > end:
        raise ValueError(f"start ({start}) must be <= end ({end})")
    today = date.today()
    if end > today + timedelta(days=1):
        raise ValueError(
            f"end date ({end}) is more than one day in the future (today={today})"
        )

    path = _cache_path(model)
    cached = _read_cache(path)
    needs_refresh = (
        cached is None
        or cached.empty
        or cached.index.min() > start
        or cached.index.max() < end
    )

    if not needs_refresh:
        assert cached is not None
        return cached

    # Build dataset key list for this model.
    if model in ("ff3", "ff5"):
        primary_key = model
    else:  # carhart4 = ff3 + Mom
        primary_key = "ff3"

    primary = _fetch_kf_dataset(primary_key)
    if model == "carhart4":
        mom = _fetch_kf_dataset("mom")
        merged = primary.join(mom, how="inner")
    else:
        merged = primary

    _write_cache(path, merged)
    # Re-read from cache to round-trip through the same dtypes as a cache hit.
    refreshed = _read_cache(path)
    assert refreshed is not None
    return refreshed


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------


def _coerce_returns(strategy_returns: pd.Series) -> pd.Series:
    """Validate and normalise the strategy_returns input.

    Accepts a pandas Series indexed by ``date`` or by datetime/Timestamp;
    returns a Series indexed by ``datetime.date`` for clean alignment with
    the factor cache.
    """
    if not isinstance(strategy_returns, pd.Series):
        raise TypeError(
            f"strategy_returns must be a pandas Series; got {type(strategy_returns).__name__}"
        )
    if strategy_returns.empty:
        raise ValueError("strategy_returns is empty")

    s = strategy_returns.copy()
    idx = s.index
    if isinstance(idx, pd.DatetimeIndex):
        s.index = idx.date
    else:
        # Coerce arbitrary date-likes to datetime.date
        coerced = []
        for v in idx:
            if isinstance(v, datetime):
                coerced.append(v.date())
            elif isinstance(v, date):
                coerced.append(v)
            else:
                coerced.append(pd.Timestamp(v).date())
        s.index = pd.Index(coerced)

    # Drop NaNs, sort by date, drop dup dates keeping the last.
    s = s.dropna()
    s = s[~s.index.duplicated(keep="last")]
    s = s.sort_index()
    return s.astype(float)


def compute_factor_exposure(
    strategy_returns: pd.Series,
    *,
    model: FactorModel = "ff3",
    risk_free_subtract: bool = True,
) -> FactorExposure:
    """Regress strategy daily returns on a Fama-French factor model.

    Parameters
    ----------
    strategy_returns:
        Daily strategy returns as a ``pd.Series`` indexed by date. Returns
        must be in fractional form (e.g. ``0.01`` for +1%, NOT ``1.0``).
    model:
        ``"ff3"`` (Mkt-RF, SMB, HML), ``"ff5"`` (adds RMW, CMA), or
        ``"carhart4"`` (ff3 + Mom).
    risk_free_subtract:
        If True (default), regress ``strategy - rf`` on the factors so the
        intercept is true alpha vs the risk-free rate. If False, regress
        the raw strategy return directly; in that case the intercept
        absorbs the average risk-free rate as well.

    Returns
    -------
    FactorExposure
        Dataclass with annualized alpha (% / year), HC1-robust SEs,
        per-factor coefficients/t-stats/p-values, R², adjusted R², n_obs
        and the inclusive date range used.

    Notes
    -----
    OLS is deterministic, so for a fixed ``strategy_returns`` series and
    a fixed factor cache the output is reproducible to floating-point
    precision (no RNG involved).
    """
    if model not in _MODEL_FACTORS:
        raise ValueError(
            f"unknown model {model!r}; expected one of {list(_MODEL_FACTORS)}"
        )

    s = _coerce_returns(strategy_returns)
    if len(s) < 2:
        raise ValueError("need at least 2 observations to fit a factor regression")

    factor_cols = _MODEL_FACTORS[model]
    factors = _load_or_fetch_factors(model, s.index.min(), s.index.max())

    needed = list(factor_cols) + ["RF"]
    missing = [c for c in needed if c not in factors.columns]
    if missing:
        raise ValueError(
            f"factor cache for {model} missing columns {missing}; got {list(factors.columns)}"
        )

    # Convert KF percent-per-day values to fractions to match strategy returns.
    f = factors[needed].astype(float) / 100.0

    aligned = pd.concat([s.rename("ret"), f], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        raise ValueError(
            f"only {len(aligned)} observation(s) after aligning strategy returns "
            f"with factor data; cannot fit"
        )

    y = aligned["ret"].to_numpy(dtype=np.float64)
    if risk_free_subtract:
        y = y - aligned["RF"].to_numpy(dtype=np.float64)

    X_df = aligned[list(factor_cols)]
    X = sm.add_constant(X_df.to_numpy(dtype=np.float64), has_constant="add")

    fit = sm.OLS(y, X).fit(cov_type="HC1")

    # Annualize alpha to % / year, matching engine.metrics.compute_alpha_beta.
    scale = TRADING_DAYS * 100.0
    alpha_daily = float(fit.params[0])
    alpha_se_daily = float(fit.bse[0])

    loadings: dict[str, FactorLoading] = {}
    for i, name in enumerate(factor_cols, start=1):
        loadings[name] = FactorLoading(
            coefficient=float(fit.params[i]),
            se=float(fit.bse[i]),
            t_stat=float(fit.tvalues[i]),
            pvalue=float(fit.pvalues[i]),
        )

    return FactorExposure(
        model=model,
        alpha=alpha_daily * scale,
        alpha_se=alpha_se_daily * scale,
        alpha_t=float(fit.tvalues[0]),
        alpha_pvalue=float(fit.pvalues[0]),
        factors=loadings,
        r_squared=float(fit.rsquared),
        adj_r_squared=float(fit.rsquared_adj),
        n_obs=int(fit.nobs),
        start_date=aligned.index.min(),
        end_date=aligned.index.max(),
        risk_free_subtracted=risk_free_subtract,
    )
