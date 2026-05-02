import pytest
from datetime import date
from data.provider import OHLCVBar
from engine.strategy import MomentumStrategy, MeanReversionStrategy, VolumeMomentumStrategy, SignalType

def create_bars(prices: list[float]) -> list[OHLCVBar]:
    return [
        OHLCVBar(
            date=date(2026, 4, 1),
            open=p,
            high=p,
            low=p,
            close=p,
            volume=1000
        )
        for p in prices
    ]

def test_momentum_strategy():
    # Price crossing above SMA(3)
    # SMA values: [None, None, 20, 30, 40]
    # Closes: [10, 20, 30, 40, 50]
    # Crossing: 
    #   i=2: prev_p=20, prev_sma=None (skip), p=30, sma=20. No cross from below.
    # We need a clear cross
    prices = [30, 30, 30, 40, 50]
    # SMA(3): [None, None, 30, 33.3, 40]
    # At index 3: price=40, sma=33.3. prev_price=30, prev_sma=30.
    # 30 <= 30 and 40 > 33.3 -> BUY
    bars = create_bars(prices)
    strat = MomentumStrategy({"sma_period": 3})
    signals = strat.generate_signals(bars)
    
    assert len(signals) == 5
    assert signals[3].type == SignalType.BUY

def test_mean_reversion_strategy():
    # RSI period 5
    # Prices: [10, 11, 12, 13, 14, 15] -> RSI=100 (overbought)
    # Prices: [15, 14, 13, 12, 11, 10] -> RSI=0 (oversold)
    bars = create_bars([15, 14, 13, 12, 11, 10])
    strat = MeanReversionStrategy({"rsi_period": 5, "oversold": 30, "overbought": 70})
    signals = strat.generate_signals(bars)
    assert signals[-1].type == SignalType.BUY

def test_volume_momentum_strategy():
    prices = [30, 30, 30, 40, 50]
    # SMA(3): [None, None, 30, 33.3, 40]
    # Price crossover buy at index 3
    
    # Case 1: High volume confirmation
    bars_high = [
        OHLCVBar(date(2026, 4, 1), p, p, p, p, 1000 if i < 3 else 2000)
        for i, p in enumerate(prices)
    ]
    # vol SMA(3): [None, None, 1000, 1333, 1666]
    # At index 3: vol=2000, v_ma=1333. 2000 > 1333 -> BUY
    strat = VolumeMomentumStrategy({"sma_period": 3, "volume_sma_period": 3})
    signals_high = strat.generate_signals(bars_high)
    assert signals_high[3].type == SignalType.BUY
    assert "high volume" in signals_high[3].reason
    
    # Case 2: Low volume -> Suppressed
    bars_low = [
        OHLCVBar(date(2026, 4, 1), p, p, p, p, 1000 if i < 3 else 500)
        for i, p in enumerate(prices)
    ]
    # vol SMA(3): [None, None, 1000, 833, 666]
    # At index 3: vol=500, v_ma=833. 500 < 833 -> HOLD
    signals_low = strat.generate_signals(bars_low)
    assert signals_low[3].type == SignalType.HOLD
    assert "volume is low" in signals_low[3].reason
