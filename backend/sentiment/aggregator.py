from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sentiment.llm_provider import (
    AnthropicProvider,
    GroqProvider,
    LLMProvider,
    OpenAIProvider,
)
from sentiment.news_fetcher import (
    NewsFetcher,
    NewsAPIFetcher,
    NewsItem,
    RedditFetcher,
    YahooNewsFetcher,
)
from sentiment.vader_scorer import VaderScorer

logger = logging.getLogger(__name__)


@dataclass
class AggregatedSentiment:
    ticker: str
    overall_score: float  # -1.0 to 1.0
    vader_avg: float
    llm_score: float | None
    trend: str  # "improving", "declining", "stable"
    num_sources: int
    headlines: list[dict] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SentimentAggregator:
    """Fetch news, score with VADER (and optionally LLM), then aggregate."""

    def __init__(self) -> None:
        self.vader = VaderScorer()
        self.fetchers: list[NewsFetcher] = []
        self.llm_provider: LLMProvider | None = None

    async def analyze_ticker(self, ticker: str) -> AggregatedSentiment:
        """Full sentiment pipeline for a single ticker."""

        # 1. Fetch news from all available fetchers concurrently
        news_items = await self._fetch_all(ticker)

        if not news_items:
            return AggregatedSentiment(
                ticker=ticker,
                overall_score=0.0,
                vader_avg=0.0,
                llm_score=None,
                trend="stable",
                num_sources=0,
            )

        # 2. Score every headline with VADER
        headline_records: list[dict] = []
        vader_scores: list[float] = []
        for item in news_items:
            text = f"{item.headline}. {item.snippet}" if item.snippet else item.headline
            score = self.vader.score(text)
            vader_scores.append(score)
            headline_records.append(
                {
                    "headline": item.headline,
                    "score": round(score, 4),
                    "source": item.source,
                    "url": item.url,
                }
            )

        vader_avg = sum(vader_scores) / len(vader_scores) if vader_scores else 0.0

        # 3. Optional LLM deep analysis on top headlines
        llm_score: float | None = None
        if self.llm_provider and self.llm_provider.is_available():
            llm_score = await self._llm_analyze(news_items[:5], ticker)

        # 4. Compute overall score (LLM overrides when available)
        if llm_score is not None:
            overall = 0.4 * vader_avg + 0.6 * llm_score
        else:
            overall = vader_avg

        overall = max(-1.0, min(1.0, overall))

        # 5. Determine trend (placeholder — needs historical data)
        trend = "stable"

        return AggregatedSentiment(
            ticker=ticker,
            overall_score=round(overall, 4),
            vader_avg=round(vader_avg, 4),
            llm_score=round(llm_score, 4) if llm_score is not None else None,
            trend=trend,
            num_sources=len(news_items),
            headlines=headline_records,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_all(self, ticker: str) -> list[NewsItem]:
        """Run all fetchers concurrently and merge results."""
        if not self.fetchers:
            return []

        tasks = [fetcher.fetch(ticker) for fetcher in self.fetchers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined: list[NewsItem] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Fetcher raised: %s", result)
                continue
            combined.extend(result)

        # Sort newest first
        combined.sort(key=lambda n: n.published_at, reverse=True)
        return combined

    async def _llm_analyze(
        self, items: list[NewsItem], ticker: str
    ) -> float | None:
        """Send a batch of headlines to the LLM provider for analysis."""
        if not self.llm_provider:
            return None
        combined_text = "\n".join(
            f"- {item.headline} ({item.source})" for item in items
        )
        try:
            result = await self.llm_provider.analyze(combined_text, ticker)
            return result.score
        except Exception as exc:
            logger.warning("LLM analysis failed: %s", exc)
            return None


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------


def create_aggregator() -> SentimentAggregator:
    """Create an aggregator wired up with all available providers."""

    agg = SentimentAggregator()

    # News fetchers — always try all; each checks its own availability
    fetcher_candidates: list[NewsFetcher] = [
        NewsAPIFetcher(),
        YahooNewsFetcher(),
        RedditFetcher(),
    ]
    agg.fetchers = [f for f in fetcher_candidates if f.is_available()]

    # LLM provider — pick the first available (preference order)
    llm_candidates: list[LLMProvider] = [
        GroqProvider(),
        OpenAIProvider(),
        AnthropicProvider(),
    ]
    for provider in llm_candidates:
        if provider.is_available():
            agg.llm_provider = provider
            logger.info("Using LLM provider: %s", provider.name)
            break

    logger.info(
        "Aggregator ready — %d fetchers, LLM: %s",
        len(agg.fetchers),
        agg.llm_provider.name if agg.llm_provider else "none",
    )
    return agg
