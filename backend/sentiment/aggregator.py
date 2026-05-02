"""Sentiment aggregator: news fetch -> VADER scoring -> single composite score.

Scope-cut version: removed multi-LLM provider abstraction and Reddit fetcher
(low signal-to-noise, hard to defend in a quant context). Sentiment is now a
clean VADER baseline over reputable news sources only. If you need a stronger
NLP layer, swap VADER for FinBERT in one place.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sentiment.news_fetcher import (
    NewsAPIFetcher,
    NewsFetcher,
    NewsItem,
    YahooNewsFetcher,
)
from sentiment.vader_scorer import VaderScorer

logger = logging.getLogger(__name__)


@dataclass
class AggregatedSentiment:
    ticker: str
    overall_score: float  # -1.0 to 1.0
    vader_avg: float
    llm_score: float | None  # kept for schema compat; always None now
    trend: str  # "improving" | "declining" | "stable"
    num_sources: int
    headlines: list[dict] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SentimentAggregator:
    """Fetch news, score with VADER, aggregate to a single score."""

    def __init__(self) -> None:
        self.vader = VaderScorer()
        self.fetchers: list[NewsFetcher] = []

    async def analyze_ticker(self, ticker: str) -> AggregatedSentiment:
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

        vader_avg = sum(vader_scores) / len(vader_scores)
        overall = max(-1.0, min(1.0, vader_avg))

        return AggregatedSentiment(
            ticker=ticker,
            overall_score=round(overall, 4),
            vader_avg=round(vader_avg, 4),
            llm_score=None,
            trend="stable",
            num_sources=len(news_items),
            headlines=headline_records,
        )

    async def _fetch_all(self, ticker: str) -> list[NewsItem]:
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
        combined.sort(key=lambda n: n.published_at, reverse=True)
        return combined


def create_aggregator() -> SentimentAggregator:
    agg = SentimentAggregator()
    candidates: list[NewsFetcher] = [NewsAPIFetcher(), YahooNewsFetcher()]
    agg.fetchers = [f for f in candidates if f.is_available()]
    logger.info("Aggregator ready — %d fetchers (VADER scoring)", len(agg.fetchers))
    return agg
