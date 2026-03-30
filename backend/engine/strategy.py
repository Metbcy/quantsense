"""Strategy interface and built-in implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .indicators import bollinger_bands, ema, macd, rsi, sma

if TYPE_CHECKING:
    pass

from data.provider import OHLCVBar


# ---------------------------------------------------------------------------
# Signal types
# ---------------------------------------------------------------------------

class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    type: SignalType
    strength: float  # 0.0 … 1.0
    reason: str


# ---------------------------------------------------------------------------
# Abstract strategy
# ---------------------------------------------------------------------------

class Strategy(ABC):
    def __init__(self, params: dict | None = None):
        self.params = params or self.default_params()

    @abstractmethod
    def default_params(self) -> dict:
        ...

    @abstractmethod
    def generate_signals(
        self,
        bars: list[OHLCVBar],
        sentiment_scores: list[float] | None = None,
    ) -> list[Signal]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...


# ---------------------------------------------------------------------------
# Momentum Strategy  (price vs SMA crossover)
# ---------------------------------------------------------------------------

class MomentumStrategy(Strategy):
    @property
    def name(self) -> str:
        return "momentum"

    @property
    def description(self) -> str:
        return "Buy when price crosses above SMA; sell when it crosses below."

    def default_params(self) -> dict:
        return {"sma_period": 20}

    def generate_signals(
        self,
        bars: list[OHLCVBar],
        sentiment_scores: list[float] | None = None,
    ) -> list[Signal]:
        closes = [b.close for b in bars]
        sma_vals = sma(closes, self.params["sma_period"])
        signals: list[Signal] = []

        for i in range(len(bars)):
            if sma_vals[i] is None or (i > 0 and sma_vals[i - 1] is None):
                signals.append(Signal(SignalType.HOLD, 0.0, "Insufficient data"))
                continue

            price = closes[i]
            ma = sma_vals[i]
            prev_price = closes[i - 1] if i > 0 else price
            prev_ma = sma_vals[i - 1] if i > 0 and sma_vals[i - 1] is not None else ma

            distance = abs(price - ma) / ma if ma != 0 else 0.0
            strength = min(distance * 10, 1.0)

            if prev_price <= prev_ma and price > ma:
                signals.append(Signal(SignalType.BUY, strength, f"Price crossed above SMA({self.params['sma_period']})"))
            elif prev_price >= prev_ma and price < ma:
                signals.append(Signal(SignalType.SELL, strength, f"Price crossed below SMA({self.params['sma_period']})"))
            else:
                signals.append(Signal(SignalType.HOLD, 0.0, "No crossover"))

        return signals


# ---------------------------------------------------------------------------
# Mean-Reversion Strategy  (RSI oversold / overbought)
# ---------------------------------------------------------------------------

class MeanReversionStrategy(Strategy):
    @property
    def name(self) -> str:
        return "mean_reversion"

    @property
    def description(self) -> str:
        return "Buy when RSI is oversold; sell when RSI is overbought."

    def default_params(self) -> dict:
        return {"rsi_period": 14, "oversold": 30, "overbought": 70}

    def generate_signals(
        self,
        bars: list[OHLCVBar],
        sentiment_scores: list[float] | None = None,
    ) -> list[Signal]:
        closes = [b.close for b in bars]
        rsi_vals = rsi(closes, self.params["rsi_period"])
        signals: list[Signal] = []

        oversold = self.params["oversold"]
        overbought = self.params["overbought"]

        for i in range(len(bars)):
            if rsi_vals[i] is None:
                signals.append(Signal(SignalType.HOLD, 0.0, "Insufficient data"))
                continue

            r = rsi_vals[i]
            if r < oversold:
                strength = min((oversold - r) / oversold, 1.0)
                signals.append(Signal(SignalType.BUY, strength, f"RSI={r:.1f} < {oversold} (oversold)"))
            elif r > overbought:
                strength = min((r - overbought) / (100 - overbought), 1.0)
                signals.append(Signal(SignalType.SELL, strength, f"RSI={r:.1f} > {overbought} (overbought)"))
            else:
                signals.append(Signal(SignalType.HOLD, 0.0, f"RSI={r:.1f} neutral"))

        return signals


# ---------------------------------------------------------------------------
# Sentiment-Momentum Strategy
# ---------------------------------------------------------------------------

class SentimentMomentumStrategy(Strategy):
    @property
    def name(self) -> str:
        return "sentiment_momentum"

    @property
    def description(self) -> str:
        return (
            "Combines SMA-crossover momentum with sentiment scores.  "
            "Suppresses buys when sentiment is strongly bearish."
        )

    def default_params(self) -> dict:
        return {"sma_period": 20, "sentiment_weight": 0.3}

    def generate_signals(
        self,
        bars: list[OHLCVBar],
        sentiment_scores: list[float] | None = None,
    ) -> list[Signal]:
        base_strategy = MomentumStrategy({"sma_period": self.params["sma_period"]})
        base_signals = base_strategy.generate_signals(bars)
        weight = self.params["sentiment_weight"]

        signals: list[Signal] = []
        for i, sig in enumerate(base_signals):
            sentiment = (
                sentiment_scores[i]
                if sentiment_scores is not None and i < len(sentiment_scores)
                else 0.0
            )

            if sig.type == SignalType.BUY:
                if sentiment <= -0.2:
                    signals.append(
                        Signal(SignalType.HOLD, 0.0, f"BUY suppressed – sentiment={sentiment:.2f}")
                    )
                else:
                    adjusted = max(0.0, min(sig.strength * (1 + sentiment * weight), 1.0))
                    signals.append(
                        Signal(
                            SignalType.BUY,
                            adjusted,
                            f"{sig.reason}; sentiment={sentiment:.2f}",
                        )
                    )
            elif sig.type == SignalType.SELL:
                adjusted = max(0.0, min(sig.strength * (1 + (-sentiment) * weight), 1.0))
                signals.append(
                    Signal(SignalType.SELL, adjusted, f"{sig.reason}; sentiment={sentiment:.2f}")
                )
            else:
                signals.append(sig)

        return signals


# ---------------------------------------------------------------------------
# Bollinger Band Strategy
# ---------------------------------------------------------------------------

class BollingerBandStrategy(Strategy):
    @property
    def name(self) -> str:
        return "bollinger_bands"

    @property
    def description(self) -> str:
        return "Buy near the lower Bollinger Band; sell near the upper band."

    def default_params(self) -> dict:
        return {"period": 20, "std_dev": 2.0}

    def generate_signals(
        self,
        bars: list[OHLCVBar],
        sentiment_scores: list[float] | None = None,
    ) -> list[Signal]:
        closes = [b.close for b in bars]
        upper, middle, lower = bollinger_bands(
            closes, self.params["period"], self.params["std_dev"]
        )
        signals: list[Signal] = []

        for i in range(len(bars)):
            if upper[i] is None or lower[i] is None or middle[i] is None:
                signals.append(Signal(SignalType.HOLD, 0.0, "Insufficient data"))
                continue

            price = closes[i]
            band_width = upper[i] - lower[i]
            if band_width == 0:
                signals.append(Signal(SignalType.HOLD, 0.0, "Zero band width"))
                continue

            if price <= lower[i]:
                strength = min((lower[i] - price) / band_width + 0.5, 1.0)
                signals.append(
                    Signal(SignalType.BUY, strength, "Price at/below lower Bollinger Band")
                )
            elif price >= upper[i]:
                strength = min((price - upper[i]) / band_width + 0.5, 1.0)
                signals.append(
                    Signal(SignalType.SELL, strength, "Price at/above upper Bollinger Band")
                )
            else:
                signals.append(Signal(SignalType.HOLD, 0.0, "Price within Bollinger Bands"))

        return signals


# ---------------------------------------------------------------------------
# MACD Strategy
# ---------------------------------------------------------------------------

class MACDStrategy(Strategy):
    @property
    def name(self) -> str:
        return "macd"

    @property
    def description(self) -> str:
        return "Buy on bullish MACD crossover; sell on bearish crossover."

    def default_params(self) -> dict:
        return {"fast": 12, "slow": 26, "signal": 9}

    def generate_signals(
        self,
        bars: list[OHLCVBar],
        sentiment_scores: list[float] | None = None,
    ) -> list[Signal]:
        closes = [b.close for b in bars]
        macd_line, signal_line, histogram = macd(
            closes, self.params["fast"], self.params["slow"], self.params["signal"]
        )
        signals: list[Signal] = []

        for i in range(len(bars)):
            if (
                histogram[i] is None
                or (i > 0 and histogram[i - 1] is None)
            ):
                signals.append(Signal(SignalType.HOLD, 0.0, "Insufficient data"))
                continue

            prev_hist = histogram[i - 1] if i > 0 else 0.0

            # Normalise strength from histogram magnitude (cap at 1.0).
            hist_abs = abs(histogram[i])  # type: ignore[arg-type]
            price = closes[i] if closes[i] != 0 else 1.0
            strength = min(hist_abs / (price * 0.02), 1.0)

            if prev_hist <= 0 and histogram[i] > 0:  # type: ignore[operator]
                signals.append(
                    Signal(SignalType.BUY, strength, "MACD bullish crossover")
                )
            elif prev_hist >= 0 and histogram[i] < 0:  # type: ignore[operator]
                signals.append(
                    Signal(SignalType.SELL, strength, "MACD bearish crossover")
                )
            else:
                signals.append(Signal(SignalType.HOLD, 0.0, "No MACD crossover"))

        return signals


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "sentiment_momentum": SentimentMomentumStrategy,
    "bollinger_bands": BollingerBandStrategy,
    "macd": MACDStrategy,
}
