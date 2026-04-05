"""Autonomous AI trading engine.

Analyzes sentiment and technicals across the watchlist, scores each ticker,
and autonomously places paper trades based on configurable thresholds.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from data.provider import OHLCVBar
from data.shared import provider as _shared_provider
from engine.indicators import bollinger_bands, macd, rsi, sma
from sentiment.aggregator import create_aggregator
from trading.broker import Order, OrderSide, OrderType
from trading.paper_broker import PaperBroker
from trading.risk_manager import RiskManager, RiskLimits
from notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


@dataclass
class TickerAnalysis:
    ticker: str
    price: float
    sentiment_score: float
    rsi_value: float | None
    sma_20: float | None
    macd_histogram: float | None
    weekly_trend: str  # "bullish", "bearish", "neutral"
    bollinger_squeeze: bool
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
        risk_manager: RiskManager | None = None,
    ):
        self.broker = broker
        self.provider = _shared_provider
        self.aggregator = create_aggregator()
        self.notifier = TelegramNotifier()
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.max_position_pct = max_position_pct
        self.max_positions = max_positions
        self.risk_manager = risk_manager or RiskManager(
            RiskLimits(
                max_position_pct=max_position_pct,
                max_open_positions=max_positions,
            )
        )
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_trading_day: date | None = None
        self.last_run: datetime | None = None
        self.last_decisions: list[AutoTradeDecision] = []

    async def analyze_ticker(self, ticker: str) -> TickerAnalysis:
        """Run full analysis on a single ticker."""
        reasons: list[str] = []

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

        # --- Daily technicals ---
        rsi_val: float | None = None
        sma_val: float | None = None
        macd_hist: float | None = None
        bb_squeeze = False
        daily_bullish: bool | None = None
        macd_score = 0.0

        try:
            end = date.today()
            start = end - timedelta(days=90)
            bars = await self.provider.get_ohlcv(ticker, start, end)
            if bars and len(bars) >= 20:
                closes = [b.close for b in bars]

                # RSI
                rsi_vals = rsi(closes, 14)
                rsi_val = rsi_vals[-1]
                if rsi_val is not None:
                    if rsi_val < 30:
                        reasons.append(f"Oversold (RSI={rsi_val:.0f})")
                    elif rsi_val > 70:
                        reasons.append(f"Overbought (RSI={rsi_val:.0f})")

                # Daily SMA-20
                sma_vals = sma(closes, 20)
                sma_val = sma_vals[-1]
                if sma_val is not None and price > 0:
                    daily_bullish = price > sma_val
                    if daily_bullish:
                        reasons.append("Price above SMA-20 (uptrend)")
                    else:
                        reasons.append("Price below SMA-20 (downtrend)")

                # MACD confirmation
                _, _, hist_vals = macd(closes)
                if len(hist_vals) >= 2:
                    h_cur = hist_vals[-1]
                    h_prev = hist_vals[-2]
                    if h_cur is not None:
                        macd_hist = h_cur
                        if h_prev is not None:
                            if h_cur > 0 and h_cur > h_prev:
                                macd_score = 0.2
                                reasons.append(f"MACD bullish confirmation (hist={h_cur:+.3f})")
                            elif h_cur < 0 and h_cur < h_prev:
                                macd_score = -0.2
                                reasons.append(f"MACD bearish confirmation (hist={h_cur:+.3f})")

                # Bollinger Band squeeze detection
                bb_upper, _, bb_lower = bollinger_bands(closes)
                non_none_bw: list[float] = []
                for i in range(len(bb_upper)):
                    u, l = bb_upper[i], bb_lower[i]
                    if u is not None and l is not None and l != 0:
                        non_none_bw.append(u - l)
                if len(non_none_bw) >= 20:
                    avg_bw = sum(non_none_bw[-20:]) / 20
                    cur_bw = non_none_bw[-1]
                    if avg_bw > 0 and cur_bw < avg_bw * 0.5:
                        bb_squeeze = True
                        reasons.append("Bollinger Band squeeze — potential breakout")
        except Exception:
            reasons.append("Technical data unavailable")

        # --- Weekly trend filter ---
        weekly_trend = "neutral"
        weekly_bullish: bool | None = None
        try:
            end_w = date.today()
            start_w = end_w - timedelta(weeks=52)
            weekly_bars = await self.provider.get_ohlcv(
                ticker, start_w, end_w, interval="1wk",
            )
            if weekly_bars and len(weekly_bars) >= 20:
                weekly_closes = [b.close for b in weekly_bars]
                weekly_sma_vals = sma(weekly_closes, 20)
                weekly_sma_val = weekly_sma_vals[-1]
                if weekly_sma_val is not None and price > 0:
                    weekly_bullish = price > weekly_sma_val
                    weekly_trend = "bullish" if weekly_bullish else "bearish"
                    reasons.append(
                        f"Weekly trend {'bullish' if weekly_bullish else 'bearish'} "
                        f"(price vs weekly SMA-20)"
                    )
        except Exception:
            logger.debug("Weekly data unavailable for %s, using daily-only scoring", ticker)
            reasons.append("Weekly data unavailable — daily-only scoring")

        # --- Composite scoring ---
        # RSI score: normalized so oversold → positive, overbought → negative
        rsi_score = 0.0
        if rsi_val is not None:
            rsi_score = max(-1.0, min(1.0, (50 - rsi_val) / 50))

        # Trend score: combines daily + weekly SMA agreement
        if daily_bullish is not None and weekly_bullish is not None:
            if daily_bullish and weekly_bullish:
                trend_score = 0.8
            elif daily_bullish and not weekly_bullish:
                trend_score = 0.2
            elif not daily_bullish and weekly_bullish:
                trend_score = -0.2
            else:
                trend_score = -0.8
        elif daily_bullish is not None:
            trend_score = 0.5 if daily_bullish else -0.5
        else:
            trend_score = 0.0

        composite = (
            0.45 * sent_score
            + 0.25 * rsi_score
            + 0.15 * macd_score
            + 0.15 * trend_score
        )
        confidence = min(abs(composite), 1.0)

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

        # Weekly trend veto: prevent buying into a downtrend
        if weekly_trend == "bearish":
            if signal == "strong_buy":
                signal = "buy"
                reasons.append("Downgraded from strong_buy — weekly trend bearish")
            elif signal == "buy":
                signal = "hold"
                reasons.append("Downgraded from buy to hold — weekly trend bearish")

        return TickerAnalysis(
            ticker=ticker,
            price=price,
            sentiment_score=sent_score,
            rsi_value=rsi_val,
            sma_20=sma_val,
            macd_histogram=macd_hist,
            weekly_trend=weekly_trend,
            bollinger_squeeze=bb_squeeze,
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

                # Pre-trade risk validation
                candidate_order = Order(
                    ticker=ticker,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    price=analysis.price,
                )
                allowed, reason = self.risk_manager.check_order(
                    candidate_order, portfolio
                )
                if not allowed:
                    logger.info("Risk check rejected BUY %s: %s", ticker, reason)
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

        # Risk-based exits on existing positions (trailing stop / take profit)
        positions_list = list(current_positions.values())
        already_selling = {d.ticker for d in decisions if d.action == "sell"}

        # Filter out positions already being sold by signal-based logic
        positions_for_risk = [
            p for p in positions_list if p.ticker not in already_selling
        ]

        for order in self.risk_manager.check_take_profit(positions_for_risk):
            decisions.append(AutoTradeDecision(
                ticker=order.ticker,
                action="sell",
                quantity=order.quantity,
                price=order.price or 0.0,
                confidence=1.0,
                reasons=["Take-profit target reached"],
            ))
            already_selling.add(order.ticker)

        # Re-filter for trailing stops (exclude any just added by take-profit)
        positions_for_trailing = [
            p for p in positions_list if p.ticker not in already_selling
        ]
        for order in self.risk_manager.update_trailing_stops(positions_for_trailing):
            decisions.append(AutoTradeDecision(
                ticker=order.ticker,
                action="sell",
                quantity=order.quantity,
                price=order.price or 0.0,
                confidence=1.0,
                reasons=["Trailing stop triggered"],
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
                execution_res = {
                    "ticker": decision.ticker,
                    "action": decision.action,
                    "status": result.status.value,
                    "filled_price": result.filled_price,
                    "quantity": result.filled_quantity,
                    "confidence": decision.confidence,
                    "reasons": decision.reasons,
                }
                results.append(execution_res)

                # Seed trailing-stop high-water mark for new buys
                if (
                    decision.action == "buy"
                    and result.status.value == "filled"
                    and result.filled_price > 0
                ):
                    self.risk_manager._high_water_marks[decision.ticker] = (
                        result.filled_price
                    )

                # Notify via Telegram
                await self.notifier.notify_execution(execution_res)

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
        # Reset daily risk tracking on a new trading day
        today = date.today()
        if self._last_trading_day is None or self._last_trading_day != today:
            portfolio = await self.broker.get_portfolio()
            self.risk_manager.reset_daily(portfolio)
            self._last_trading_day = today

        decisions = await self.make_decisions(tickers)
        results = await self.execute_decisions(decisions)
        portfolio = await self.broker.get_portfolio()

        res = {
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
        
        # Notify cycle summary
        await self.notifier.notify_cycle_summary(res)
        
        return res
