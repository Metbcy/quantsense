"""Tests for engine.factors and the /factor-exposure API endpoint.

Network-dependent tests (live fetch from Kenneth French's data library)
are gated behind ``RUN_NETWORK_TESTS``; everything else runs against a
mocked fetcher so the suite is fully offline by default.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from engine import factors as factors_mod
from engine.factors import (
    FactorExposure,
    FactorLoading,
    compute_factor_exposure,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Every test gets its own cache dir so cache state never leaks."""
    monkeypatch.setenv("QUANTSENSE_FACTOR_CACHE_DIR", str(tmp_path))
    yield


def _make_factor_frame(
    n: int = 600, *, seed: int = 0, with_carhart: bool = False
) -> pd.DataFrame:
    """Build a synthetic factor table that mimics Kenneth French daily data
    (percent units, with an RF column)."""
    rng = np.random.default_rng(seed)
    start = date(2018, 1, 2)
    idx = pd.bdate_range(start, periods=n).date  # business days only

    # Factor returns ~ N(0, 0.01) in fractional units, then *100 to mimic KF pct.
    mkt = rng.normal(0.0004, 0.01, n) * 100.0
    smb = rng.normal(0.0001, 0.005, n) * 100.0
    hml = rng.normal(0.0001, 0.005, n) * 100.0
    rmw = rng.normal(0.0, 0.004, n) * 100.0
    cma = rng.normal(0.0, 0.004, n) * 100.0
    mom = rng.normal(0.0002, 0.006, n) * 100.0
    rf = np.full(n, 0.01)  # ~2.5% / yr in pct/day

    cols: dict[str, np.ndarray] = {
        "Mkt-RF": mkt,
        "SMB": smb,
        "HML": hml,
        "RMW": rmw,
        "CMA": cma,
        "RF": rf,
    }
    if with_carhart:
        cols["Mom"] = mom
    df = pd.DataFrame(cols, index=pd.Index(idx, name="date"))
    return df


@pytest.fixture
def patch_fetcher(monkeypatch):
    """Patch the network fetcher with a counter so we can assert cache hit/miss."""
    calls = {"n": 0, "by_key": []}

    full = _make_factor_frame(n=800, seed=42, with_carhart=True)

    def _fake(dataset_key: str) -> pd.DataFrame:
        calls["n"] += 1
        calls["by_key"].append(dataset_key)
        if dataset_key == "ff3":
            return full[["Mkt-RF", "SMB", "HML", "RF"]].copy()
        if dataset_key == "ff5":
            return full[["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]].copy()
        if dataset_key == "mom":
            return full[["Mom"]].copy()
        raise AssertionError(f"unexpected dataset key {dataset_key}")

    monkeypatch.setattr(factors_mod, "_fetch_kf_dataset", _fake)
    return calls


# ---------------------------------------------------------------------------
# Pure regression behaviour
# ---------------------------------------------------------------------------


def test_recovers_known_betas(patch_fetcher):
    """Strategy = 1.2 * Mkt-RF + 0.3 * SMB + tiny noise → coefficients match."""
    full = _make_factor_frame(n=800, seed=7, with_carhart=False)
    # Inject the same frame our fake fetcher returns.
    factors_mod._fetch_kf_dataset.__wrapped__ = None  # type: ignore[attr-defined]

    # Build strategy returns from the synthetic factors *and* monkeypatch the
    # fetcher to return that same frame so alignment is exact.
    rng = np.random.default_rng(11)
    mkt_rf = full["Mkt-RF"].to_numpy() / 100.0
    smb = full["SMB"].to_numpy() / 100.0
    rf = full["RF"].to_numpy() / 100.0
    noise = rng.normal(0.0, 1e-5, len(full))  # very small ε to make coefs tight

    # In risk_free_subtract mode the fit is on (strategy - rf), so the data-
    # generating process should also be (strategy - rf) = β·factors + ε:
    strat_excess = 1.2 * mkt_rf + 0.3 * smb + noise
    strategy_returns = strat_excess + rf  # add rf back; the fit subtracts it

    series = pd.Series(strategy_returns, index=pd.Index(full.index))

    # Re-patch fetcher to return the SAME synthetic frame the strategy was
    # generated from.
    def _fake_exact(dataset_key: str) -> pd.DataFrame:
        if dataset_key == "ff3":
            return full[["Mkt-RF", "SMB", "HML", "RF"]].copy()
        raise AssertionError(dataset_key)

    import engine.factors as fmod

    fmod._fetch_kf_dataset = _fake_exact  # type: ignore[assignment]

    res = compute_factor_exposure(series, model="ff3")
    assert isinstance(res, FactorExposure)
    assert res.model == "ff3"
    assert res.n_obs == len(full)
    assert "Mkt-RF" in res.factors and "SMB" in res.factors and "HML" in res.factors

    assert res.factors["Mkt-RF"].coefficient == pytest.approx(1.2, rel=0.05)
    assert res.factors["SMB"].coefficient == pytest.approx(0.3, rel=0.05)
    # HML coefficient should be ~0 (we didn't load on it).
    assert abs(res.factors["HML"].coefficient) < 0.05
    # R² should be very high since noise is tiny.
    assert res.r_squared > 0.99


def test_alpha_is_recovered_when_injected(patch_fetcher):
    """Inject 0.0001 / day alpha (~2.5% annualized) and confirm we get it back."""
    full = _make_factor_frame(n=900, seed=23, with_carhart=False)

    rng = np.random.default_rng(31)
    mkt_rf = full["Mkt-RF"].to_numpy() / 100.0
    rf = full["RF"].to_numpy() / 100.0

    daily_alpha = 0.0001  # 252 * 0.0001 * 100 = 2.52% annualized
    noise = rng.normal(0.0, 5e-4, len(full))
    strat_excess = daily_alpha + 1.0 * mkt_rf + noise
    strategy_returns = strat_excess + rf

    series = pd.Series(strategy_returns, index=pd.Index(full.index))

    import engine.factors as fmod

    fmod._fetch_kf_dataset = lambda key: full[  # type: ignore[assignment]
        ["Mkt-RF", "SMB", "HML", "RF"]
    ].copy()

    res = compute_factor_exposure(series, model="ff3")
    expected_alpha_pct = daily_alpha * 252 * 100  # ≈ 2.52
    # ~0.4% annualized SE on the intercept with 5e-4 noise over 900 obs;
    # use a 1% tolerance to keep it >2σ but still meaningfully tight.
    assert res.alpha == pytest.approx(expected_alpha_pct, abs=1.0)
    # And alpha should be highly significant given large n and small noise.
    assert abs(res.alpha_t) > 3.0


def test_risk_free_subtract_flag_changes_alpha(patch_fetcher):
    """Toggling risk_free_subtract shifts the intercept by ~RF·252·100."""
    full = _make_factor_frame(n=500, seed=5, with_carhart=False)
    rng = np.random.default_rng(2)
    mkt_rf = full["Mkt-RF"].to_numpy() / 100.0
    rf = full["RF"].to_numpy() / 100.0

    strat = 1.0 * mkt_rf + rng.normal(0.0, 1e-4, len(full)) + rf
    series = pd.Series(strat, index=pd.Index(full.index))

    import engine.factors as fmod

    fmod._fetch_kf_dataset = lambda key: full[  # type: ignore[assignment]
        ["Mkt-RF", "SMB", "HML", "RF"]
    ].copy()

    with_rf = compute_factor_exposure(series, model="ff3", risk_free_subtract=True)
    without_rf = compute_factor_exposure(series, model="ff3", risk_free_subtract=False)

    # Mean RF in pct/yr ≈ 0.01 * 252 ≈ 2.52
    expected_shift = float(np.mean(rf)) * 252 * 100
    assert without_rf.alpha == pytest.approx(with_rf.alpha + expected_shift, abs=0.1)
    assert with_rf.risk_free_subtracted is True
    assert without_rf.risk_free_subtracted is False


# ---------------------------------------------------------------------------
# Cache + alignment
# ---------------------------------------------------------------------------


def test_cache_hit_then_miss(tmp_path, monkeypatch):
    """Second call with the same range MUST NOT hit the network."""
    monkeypatch.setenv("QUANTSENSE_FACTOR_CACHE_DIR", str(tmp_path))

    full = _make_factor_frame(n=600, seed=99, with_carhart=False)
    calls = {"n": 0}

    def _fake(dataset_key: str) -> pd.DataFrame:
        calls["n"] += 1
        return full[["Mkt-RF", "SMB", "HML", "RF"]].copy()

    monkeypatch.setattr(factors_mod, "_fetch_kf_dataset", _fake)

    rng = np.random.default_rng(1)
    series = pd.Series(
        rng.normal(0.0, 0.01, len(full)) + full["Mkt-RF"].to_numpy() / 100.0,
        index=pd.Index(full.index),
    )

    res1 = compute_factor_exposure(series, model="ff3")
    assert calls["n"] == 1
    assert (tmp_path / "factors_ff3.parquet").exists()

    # Second call: cache covers the range, fetcher must NOT be invoked.
    res2 = compute_factor_exposure(series, model="ff3")
    assert calls["n"] == 1, "second call hit the network — cache is broken"
    assert res1.r_squared == pytest.approx(res2.r_squared, rel=1e-12)
    assert res1.factors["Mkt-RF"].coefficient == pytest.approx(
        res2.factors["Mkt-RF"].coefficient, rel=1e-12
    )


def test_n_obs_respects_alignment(patch_fetcher):
    """Strategy returns sparser than factor coverage → n_obs = intersection."""
    full = _make_factor_frame(n=400, seed=3, with_carhart=False)

    import engine.factors as fmod

    fmod._fetch_kf_dataset = lambda key: full[  # type: ignore[assignment]
        ["Mkt-RF", "SMB", "HML", "RF"]
    ].copy()

    # Take only the middle slice of the strategy series.
    sliced_dates = full.index[100:250]
    rng = np.random.default_rng(4)
    series = pd.Series(
        rng.normal(0.0, 0.01, len(sliced_dates)),
        index=pd.Index(sliced_dates),
    )

    res = compute_factor_exposure(series, model="ff3")
    assert res.n_obs == len(sliced_dates)
    assert res.start_date == sliced_dates[0]
    assert res.end_date == sliced_dates[-1]


# ---------------------------------------------------------------------------
# Validation / error paths
# ---------------------------------------------------------------------------


def test_bad_date_range_rejected():
    """start > end is rejected loudly."""
    # _coerce_returns sorts, so to actually trigger the start>end check on
    # the cache loader directly we test it with a clearly-future end:
    with pytest.raises(ValueError, match="future"):
        factors_mod._load_or_fetch_factors(
            "ff3",
            date.today() + timedelta(days=400),
            date.today() + timedelta(days=400),
        )

    with pytest.raises(ValueError, match="must be <="):
        factors_mod._load_or_fetch_factors("ff3", date(2020, 6, 1), date(2020, 1, 1))


def test_unknown_model_rejected():
    series = pd.Series(
        [0.001, -0.001], index=pd.Index([date(2020, 1, 2), date(2020, 1, 3)])
    )
    with pytest.raises(ValueError, match="unknown model"):
        compute_factor_exposure(series, model="ff7")  # type: ignore[arg-type]


def test_carhart4_uses_momentum(patch_fetcher):
    """carhart4 model should pull in the Mom factor."""
    full = _make_factor_frame(n=500, seed=8, with_carhart=True)

    rng = np.random.default_rng(9)
    mkt_rf = full["Mkt-RF"].to_numpy() / 100.0
    mom = full["Mom"].to_numpy() / 100.0
    rf = full["RF"].to_numpy() / 100.0
    strat = 1.0 * mkt_rf + 0.5 * mom + rng.normal(0.0, 1e-5, len(full)) + rf
    series = pd.Series(strat, index=pd.Index(full.index))

    import engine.factors as fmod

    def _fake(key: str) -> pd.DataFrame:
        if key == "ff3":
            return full[["Mkt-RF", "SMB", "HML", "RF"]].copy()
        if key == "mom":
            return full[["Mom"]].copy()
        raise AssertionError(key)

    fmod._fetch_kf_dataset = _fake  # type: ignore[assignment]

    res = compute_factor_exposure(series, model="carhart4")
    assert "Mom" in res.factors
    assert res.factors["Mom"].coefficient == pytest.approx(0.5, rel=0.05)
    assert res.factors["Mkt-RF"].coefficient == pytest.approx(1.0, rel=0.05)


def test_dataclass_to_dict_roundtrips():
    fl = FactorLoading(coefficient=1.2, se=0.05, t_stat=24.0, pvalue=1e-30)
    fe = FactorExposure(
        model="ff3",
        alpha=2.5,
        alpha_se=0.4,
        alpha_t=6.25,
        alpha_pvalue=1e-9,
        factors={"Mkt-RF": fl},
        r_squared=0.92,
        adj_r_squared=0.91,
        n_obs=500,
        start_date=date(2020, 1, 2),
        end_date=date(2021, 12, 31),
    )
    d = fe.to_dict()
    assert d["model"] == "ff3"
    assert d["factors"]["Mkt-RF"]["coefficient"] == 1.2
    assert d["start_date"] == "2020-01-02"
    assert d["end_date"] == "2021-12-31"
    assert d["risk_free_subtracted"] is True


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """Spin up the FastAPI app with a per-test cache dir + mocked fetcher."""
    monkeypatch.setenv("QUANTSENSE_FACTOR_CACHE_DIR", str(tmp_path / "fcache"))

    full = _make_factor_frame(n=500, seed=17, with_carhart=False)

    def _fake(key: str) -> pd.DataFrame:
        if key == "ff3":
            return full[["Mkt-RF", "SMB", "HML", "RF"]].copy()
        raise AssertionError(key)

    monkeypatch.setattr(factors_mod, "_fetch_kf_dataset", _fake)

    # Force test sqlite (matches conftest pattern).
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_quantsense.db")
    from main import app

    return TestClient(app), full


def test_api_factor_exposure_explicit(api_client):
    client, full = api_client
    rng = np.random.default_rng(0)
    mkt_rf = full["Mkt-RF"].to_numpy() / 100.0
    rf = full["RF"].to_numpy() / 100.0
    rets = 1.1 * mkt_rf + rng.normal(0.0, 5e-5, len(full)) + rf

    payload = {
        "returns": rets.tolist(),
        "dates": [d.isoformat() for d in full.index],
        "model": "ff3",
    }
    resp = client.post("/api/backtest/factor-exposure", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model"] == "ff3"
    assert "Mkt-RF" in body["factors"]
    assert body["factors"]["Mkt-RF"]["coefficient"] == pytest.approx(1.1, rel=0.05)
    assert body["n_obs"] == len(full)


def test_api_rejects_both_or_neither_input(api_client):
    client, _ = api_client
    # Neither
    resp = client.post("/api/backtest/factor-exposure", json={"model": "ff3"})
    assert resp.status_code == 422
    # Both
    resp = client.post(
        "/api/backtest/factor-exposure",
        json={
            "result_id": 1,
            "returns": [0.001, -0.001],
            "dates": ["2020-01-02", "2020-01-03"],
            "model": "ff3",
        },
    )
    assert resp.status_code == 422


def test_api_404_unknown_result(api_client):
    client, _ = api_client
    resp = client.post(
        "/api/backtest/factor-exposure",
        json={"result_id": 99999, "model": "ff3"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Live network test (skipped by default)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("RUN_NETWORK_TESTS"),
    reason="set RUN_NETWORK_TESTS=1 to enable live Kenneth French fetch",
)
def test_live_kf_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTSENSE_FACTOR_CACHE_DIR", str(tmp_path))
    df = factors_mod._load_or_fetch_factors("ff3", date(2020, 1, 1), date(2020, 12, 31))
    assert {"Mkt-RF", "SMB", "HML", "RF"}.issubset(df.columns)
    assert df.index.min() <= date(2020, 1, 5)
    assert df.index.max() >= date(2020, 12, 28)
