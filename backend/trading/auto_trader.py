"""Autonomous AI trading engine.

Analyzes sentiment and technicals across the watchlist, scores each ticker,
and autonomously places paper trades based on configurable thresholds.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from data.provider import OHLCVBar
from data.yahoo_provider import YahooFinanceProvider
from engine.indicators import rsi, sma
from sentiment.aggregator import create_aggregator
from trading.broker import Order, OrderSide, OrderType
from trading.paper_broker import PaperBroker

logger = logging.getLogger(__name__)


@dataclass
class TickerAnalysis:
    ticker: str
    price: float
    sentiment_score: float
    rsi_value: float | None
    sma_20: float | None
    signal: str  # "strong_buy", "buy", "hold", "sell", "strong_sell"
    confidence: float  # 0.0 to 1.0
    reasons: list[str]


@dataclass
class AutoTradeDecision:
    ticker: str
    action: str  # "buy", "sell", "hold"
    quantity: float
    price: float
    confidence: float
    reasons: list[str]


class AutoTrader:
    """AI-powered autonomous trading engine."""

    def __init__(
        self,
        broker: PaperBroker,
        buy_threshold: float = 0.3,
        sell_threshold: float = -0.2,
        max_position_pct: float = 0.20,
        max_positions: int = 5,
    ):
        self.broker = broker
        self.provider = YahooFinanceProvider()
        self.aggregator = create_aggregator()
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.max_position_pct = max_position_pct
        self.max_positions = max_positions
        self._running = False
        self._task: asyncio.Task | None = None
        self.last_run: datetime | None = None
        self.last_decisions: list[AutoTradeDecision] = []

    async def analyze_ticker(self, ticker: str) -> TickerAnalysis:
        """Run full analysis on a single ticker."""
        reasons = []

        # Get current quote
        quote = await self.provider.get_quote(ticker)
        price = quote.price if quote.price > 0 else 0.0

        # Get sentiment
        try:
            sentiment = await self.aggregator.analyze_ticker(ticker)
            sent_score = sentiment.overall_score
            if sent_score > 0.3:
                reasons.append(f"Bullish sentiment ({sent_score:+.2f})")
            elif sent_score < -0.3:
                reasons.append(f"Bearish sentiment ({sent_score:+.2f})")
        except Exception:
            sent_score = 0.0
            reasons.append("Sentiment unavailable")

        # Get technicals (last 60 days)
        rsi_val = None
        sma_val = None
        try:
            end = date.today()
            start = end - timedelta(days=90)
            bars = await self.provider.get_ohlcv(ticker, start, end)
            if bars and len(bars) >= 20:
                closes = [b.close for b in bars]
                rsi_vals = rsi(closes, 14)
                rsi_val = rsi_vals[-1]
                sma_vals = sma(closes, 20)
                sma_val = sma_vals[-1]

                if rsi_val is not None:
                    if rsi_val < 30:
                        reasons.append(f"Oversold (RSI={rsi_val:.0f})")
                    elif rsi_val > 70:
                        reasons.append(f"Overbought (RSI={rsi_val:.0f})")

                if sma_val is not None and price > 0:
                    if price > sma_val:
                        reasons.append("Price above SMA-20 (uptrend)")
                    else:
                        reasons.append("Price below SMA-20 (downtrend)")
        except Exception:
            reasons.append("Technical data unavailable")

        # Composite score: 60% sentiment, 40% technicals
        tech_score = 0.0
        if rsi_val is not None:
            tech_score += (50 - rsi_val) / 50 * 0.5  # RSI contribution
        if sma_val is not None and price > 0:
            tech_score += (price - sma_val) / sma_val * 2  # Trend contribution
        tech_score = max(-1, min(1, tech_score))

        composite = sent_score * 0.6 + tech_score * 0.4
        confidence = abs(composite)

        if composite > 0.5:
            signal = "strong_buy"
        elif composite > self.buy_threshold:
            signal = "buy"
        elif composite < -0.5:
            signal = "strong_sell"
        elif composite < self.sell_threshold:
            signal = "sell"
        else:
            signal = "hold"

        return TickerAnalysis(
            ticker=ticker,
            price=price,
            sentiment_score=sent_score,
            rsi_value=rsi_val,
            sma_20=sma_val,
            signal=signal,
            confidence=confidence,
            reasons=reasons,
        )

    async def make_decisions(self, tickers: list[str]) -> list[AutoTradeDecision]:
        """Analyze all tickers and generate trade decisions."""
        decisions: list[AutoTradeDecision] = []
        portfolio = await self.broker.get_portfolio()
        current_positions = {p.ticker: p for p in portfolio.positions}

        analyses = []
        for ticker in tickers:
            try:
                analysis = await self.analyze_ticker(ticker)
                analyses.append(analysis)
            except Exception as e:
                logger.warning("Failed to analyze %s: %s", ticker, e)

        # Sort by confidence descending
        analyses.sort(key=lambda a: a.confidence, reverse=True)

        for analysis in analyses:
            ticker = analysis.ticker
            in_position = ticker in current_positions

            if analysis.signal in ("strong_buy", "buy") and not in_position:
                # Only buy if we have room for more positions
                if len(current_positions) >= self.max_positions:
                    continue
                # Calculate position size
                max_invest = portfolio.total_value * self.max_position_pct
                available = min(portfolio.cash * 0.95, max_invest)
                if available < 100 or analysis.price <= 0:
                    continue
                quantity = int(available / analysis.price)
                if quantity <= 0:
                    continue
                decisions.append(AutoTradeDecision(
                    ticker=ticker,
                    action="buy",
                    quantity=quantity,
                    price=analysis.price,
                    confidence=analysis.confidence,
                    reasons=analysis.reasons,
                ))

            elif analysis.signal in ("strong_sell", "sell") and in_position:
                pos = current_positions[ticker]
                decisions.append(AutoTradeDecision(
                    ticker=ticker,
                    action="sell",
                    quantity=pos.quantity,
                    price=analysis.price,
                    confidence=analysis.confidence,
                    reasons=analysis.reasons,
                ))

            else:
                decisions.append(AutoTradeDecision(
                    ticker=ticker,
                    action="hold",
                    quantity=0,
                    price=analysis.price,
                    confidence=analysis.confidence,
                    reasons=analysis.reasons,
                ))

        self.last_decisions = decisions
        self.last_run = datetime.now()
        return decisions

    async def execute_decisions(self, decisions: list[AutoTradeDecision]) -> list[dict]:
        """Execute trade decisions through the broker."""
        results = []
        for decision in decisions:
            if decision.action == "hold":
                results.append({
                    "ticker": decision.ticker,
                    "action": "hold",
                    "status": "skipped",
                    "reasons": decision.reasons,
                })
                continue

            order = Order(
                ticker=decision.ticker,
                side=OrderSide.BUY if decision.action == "buy" else OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=decision.quantity,
                price=decision.price,
            )

            try:
                result = await self.broker.submit_order(order)
                results.append({
                    "ticker": decision.ticker,
                    "action": decision.action,
                    "status": result.status.value,
                    "filled_price": result.filled_price,
                    "quantity": result.filled_quantity,
                    "confidence": decision.confidence,
                    "reasons": decision.reasons,
                })
                logger.info(
                    "Auto-trade: %s %s x%.0f @ $%.2f (confidence: %.0f%%)",
                    decision.action.upper(),
                    decision.ticker,
                    decision.quantity,
                    decision.price,
                    decision.confidence * 100,
                )
            except Exception as e:
                results.append({
                    "ticker": decision.ticker,
                    "action": decision.action,
                    "status": "error",
                    "error": str(e),
                    "reasons": decision.reasons,
                })

        return results

    async def run_cycle(self, tickers: list[str]) -> dict:
        """Run one full analysis + trade cycle."""
        decisions = await self.make_decisions(tickers)
        results = await self.execute_decisions(decisions)
        portfolio = await self.broker.get_portfolio()

        return {
            "timestamp": datetime.now().isoformat(),
            "decisions": [
                {
                    "ticker": d.ticker,
                    "action": d.action,
                    "quantity": d.quantity,
                    "price": d.price,
                    "confidence": d.confidence,
                    "reasons": d.reasons,
                }
                for d in decisions
            ],
            "executions": results,
            "portfolio": {
                "total_value": portfolio.total_value,
                "cash": portfolio.cash,
                "positions_count": len(portfolio.positions),
                "total_pnl": portfolio.total_pnl,
                "total_pnl_pct": portfolio.total_pnl_pct,
            },
        }
