import pytest
import numpy as np
from engine.indicators import sma, ema, rsi, macd, bollinger_bands

def test_sma():
    prices = [10.0, 20.0, 30.0, 40.0, 50.0]
    # Period 3: 
    # [None, None, (10+20+30)/3, (20+30+40)/3, (30+40+50)/3]
    # [None, None, 20.0, 30.0, 40.0]
    res = sma(prices, 3)
    assert len(res) == 5
    assert res[0] is None
    assert res[1] is None
    assert np.isclose(res[2], 20.0)
    assert np.isclose(res[3], 30.0)
    assert np.isclose(res[4], 40.0)

def test_ema():
    prices = [10.0, 20.0, 30.0, 40.0, 50.0]
    # Period 3:
    # SMA of first 3 = 20.0
    # Multiplier = 2 / (3 + 1) = 0.5
    # EMA_3 = 20.0
    # EMA_4 = 40.0 * 0.5 + 20.0 * (1 - 0.5) = 20 + 10 = 30.0
    # EMA_5 = 50.0 * 0.5 + 30.0 * (1 - 0.5) = 25 + 15 = 40.0
    res = ema(prices, 3)
    assert len(res) == 5
    assert res[0] is None
    assert res[1] is None
    assert np.isclose(res[2], 20.0)
    assert np.isclose(res[3], 30.0)
    assert np.isclose(res[4], 40.0)

def test_rsi():
    # Constant prices -> RSI should be neutral or None if all same, but let's use a trend
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    # Period 5. diffs: [1, 1, 1, 1, 1]
    # All gains. RSI should be 100.
    res = rsi(prices, 5)
    assert len(res) == 6
    assert res[4] is None
    assert np.isclose(res[5], 100.0)

def test_macd():
    prices = [10.0] * 40 # Stable prices
    macd_line, signal_line, hist = macd(prices, 12, 26, 9)
    assert len(macd_line) == 40
    # On stable prices, MACD line should eventually be close to 0
    if macd_line[-1] is not None:
        assert np.isclose(macd_line[-1], 0.0, atol=1e-5)

def test_bollinger_bands():
    prices = [10.0, 11.0, 10.0, 11.0, 10.0]
    upper, middle, lower = bollinger_bands(prices, 2, 2.0)
    assert len(upper) == 5
    assert middle[0] is None
    assert np.isclose(middle[1], 10.5)
    # std of [10, 11] is 0.5
    # upper = 10.5 + 2 * 0.5 = 11.5
    # lower = 10.5 - 2 * 0.5 = 9.5
    assert np.isclose(upper[1], 11.5)
    assert np.isclose(lower[1], 9.5)
