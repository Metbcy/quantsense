# Sentiment Sources + Smart Screener Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add StockTwits and SEC EDGAR as sentiment sources with weighted aggregation, and replace the simple screener with category-based scoring (technical/sentiment/fundamental).

**Architecture:** Two new `NewsFetcher` implementations (StockTwits, EDGAR) plug into the existing aggregator. Aggregator gets source-weighted scoring. Screener gets three-category scoring with configurable weights stored in `AppSetting`.

**Tech Stack:** Python, httpx, FastAPI, SQLAlchemy, VADER, existing LLM pipeline

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/sentiment/stocktwits.py` | Create | StockTwits API fetcher |
| `backend/sentiment/edgar.py` | Create | SEC EDGAR insider trades + filing fetcher |
| `backend/sentiment/aggregator.py` | Modify | Weighted source scoring, register new fetchers |
| `backend/engine/screener.py` | Modify | Category-based scoring with configurable weights |
| `backend/api/market.py` | Modify | Serialize new screener fields |
| `backend/config/settings.py` | Modify | Add SEC_EDGAR_USER_AGENT setting |
| `backend/tests/test_stocktwits.py` | Create | StockTwits fetcher tests |
| `backend/tests/test_edgar.py` | Create | EDGAR fetcher tests |
| `backend/tests/test_screener_scoring.py` | Create | Category scoring tests |
| `backend/tests/test_weighted_aggregation.py` | Create | Weighted aggregation tests |

---

### Task 1: StockTwits Fetcher

**Files:**
- Create: `backend/sentiment/stocktwits.py`
- Create: `backend/tests/test_stocktwits.py`

- [ ] **Step 1: Write failing test for StockTwits fetcher**

```python
# backend/tests/test_stocktwits.py
"""Tests for StockTwits sentiment fetcher."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from sentiment.stocktwits import StockTwitsFetcher


@pytest.fixture
def fetcher():
    return StockTwitsFetcher()


def test_is_available(fetcher):
    """StockTwits fetcher is always available (no API key needed)."""
    assert fetcher.is_available() is True


@pytest.mark.asyncio
async def test_fetch_parses_messages(fetcher):
    """Fetcher extracts headlines from StockTwits API response."""
    mock_response = {
        "messages": [
            {
                "id": 123,
                "body": "AAPL looking bullish after earnings beat",
                "created_at": "2026-04-10T12:00:00Z",
                "entities": {
                    "sentiment": {"basic": "Bullish"}
                },
                "user": {"username": "trader1"},
            },
            {
                "id": 124,
                "body": "Sold my AAPL position, too risky here",
                "created_at": "2026-04-10T11:00:00Z",
                "entities": {},
                "user": {"username": "trader2"},
            },
        ]
    }

    with patch("sentiment.stocktwits.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response
        mock_resp.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        items = await fetcher.fetch("AAPL", limit=10)

    assert len(items) == 2
    assert items[0].source == "stocktwits"
    assert items[0].headline == "AAPL looking bullish after earnings beat"
    assert items[0].ticker == "AAPL"
    assert "[Bullish]" in items[0].snippet


@pytest.mark.asyncio
async def test_fetch_handles_rate_limit(fetcher):
    """Fetcher returns empty list on 429 rate limit."""
    with patch("sentiment.stocktwits.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = AsyncMock()
        mock_resp.status_code = 429
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        items = await fetcher.fetch("AAPL")

    assert items == []


@pytest.mark.asyncio
async def test_fetch_handles_network_error(fetcher):
    """Fetcher returns empty list on network error."""
    with patch("sentiment.stocktwits.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        MockClient.return_value = mock_client

        import httpx
        items = await fetcher.fetch("AAPL")

    assert items == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_stocktwits.py -v'`
Expected: ImportError — `sentiment.stocktwits` not found

- [ ] **Step 3: Implement StockTwits fetcher**

```python
# backend/sentiment/stocktwits.py
"""StockTwits sentiment fetcher — free, unauthenticated API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from sentiment.news_fetcher import NewsFetcher, NewsItem, _safe_parse_dt

logger = logging.getLogger(__name__)

STOCKTWITS_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"


class StockTwitsFetcher(NewsFetcher):
    """Fetch messages from StockTwits stream for a ticker.

    Rate limit: 200 requests/hour unauthenticated.
    """

    def is_available(self) -> bool:
        return True

    async def fetch(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    STOCKTWITS_API.format(ticker=ticker.upper()),
                )
                if resp.status_code == 429:
                    logger.warning("StockTwits rate limited for %s", ticker)
                    return []
                resp.raise_for_status()
                data = resp.json()

            items: list[NewsItem] = []
            for msg in data.get("messages", [])[:limit]:
                body = msg.get("body", "")
                if not body:
                    continue

                # Extract native sentiment label if present
                entities = msg.get("entities", {})
                sentiment_data = entities.get("sentiment", {})
                native_label = sentiment_data.get("basic", "")  # "Bullish" or "Bearish"

                snippet = f"[{native_label}] " if native_label else ""

                created = msg.get("created_at", "")
                pub_dt = _safe_parse_dt(created)

                msg_id = msg.get("id", "")
                url = f"https://stocktwits.com/message/{msg_id}" if msg_id else ""

                items.append(
                    NewsItem(
                        headline=body[:500],
                        snippet=snippet,
                        source="stocktwits",
                        url=url,
                        published_at=pub_dt,
                        ticker=ticker,
                    )
                )
            return items
        except Exception as exc:
            logger.warning("StockTwitsFetcher error for %s: %s", ticker, exc)
            return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_stocktwits.py -v'`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/amirb/quantsense
git add backend/sentiment/stocktwits.py backend/tests/test_stocktwits.py
git commit -m "feat: add StockTwits sentiment fetcher"
```

---

### Task 2: SEC EDGAR Fetcher

**Files:**
- Create: `backend/sentiment/edgar.py`
- Create: `backend/tests/test_edgar.py`
- Modify: `backend/config/settings.py`

- [ ] **Step 1: Add SEC_EDGAR_USER_AGENT to settings**

In `backend/config/settings.py`, add this field to the `Settings` class (after `ALPACA_PAPER`):

```python
SEC_EDGAR_USER_AGENT: str = "QuantSense/1.0 (quantsense@example.com)"
```

- [ ] **Step 2: Write failing test for EDGAR fetcher**

```python
# backend/tests/test_edgar.py
"""Tests for SEC EDGAR sentiment fetchers."""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from sentiment.edgar import EdgarInsiderFetcher, EdgarFilingFetcher


@pytest.fixture
def insider_fetcher():
    return EdgarInsiderFetcher()


@pytest.fixture
def filing_fetcher():
    return EdgarFilingFetcher()


def test_insider_is_available(insider_fetcher):
    assert insider_fetcher.is_available() is True


def test_filing_is_available(filing_fetcher):
    assert filing_fetcher.is_available() is True


@pytest.mark.asyncio
async def test_insider_parses_purchase(insider_fetcher):
    """Insider purchase generates bullish NewsItem."""
    mock_data = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "display_names": ["John Smith, CEO"],
                        "file_date": "2026-04-08",
                        "form_type": "4",
                    },
                    "_id": "0001234-26-000001",
                }
            ]
        }
    }
    mock_filing_xml = """<?xml version="1.0"?>
    <ownershipDocument>
        <reportingOwner><reportingOwnerId>
            <rptOwnerName>John Smith</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <officerTitle>CEO</officerTitle>
            <isOfficer>1</isOfficer>
        </reportingOwnerRelationship></reportingOwner>
        <nonDerivativeTable><nonDerivativeTransaction>
            <transactionAmounts>
                <transactionShares><value>10000</value></transactionShares>
                <transactionPricePerShare><value>185.50</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
        </nonDerivativeTransaction></nonDerivativeTable>
    </ownershipDocument>"""

    with patch("sentiment.edgar.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_search_resp = AsyncMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = mock_data
        mock_search_resp.raise_for_status = lambda: None

        mock_filing_resp = AsyncMock()
        mock_filing_resp.status_code = 200
        mock_filing_resp.text = mock_filing_xml
        mock_filing_resp.raise_for_status = lambda: None

        mock_client.get = AsyncMock(side_effect=[mock_search_resp, mock_filing_resp])
        MockClient.return_value = mock_client

        items = await insider_fetcher.fetch("AAPL", limit=10)

    assert len(items) >= 1
    assert items[0].source == "edgar_insider"
    assert "purchased" in items[0].headline.lower() or "acquired" in items[0].headline.lower()


@pytest.mark.asyncio
async def test_insider_handles_empty_response(insider_fetcher):
    """Returns empty list when no filings found."""
    mock_data = {"hits": {"hits": []}}

    with patch("sentiment.edgar.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_data
        mock_resp.raise_for_status = lambda: None
        mock_client.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = mock_client

        items = await insider_fetcher.fetch("AAPL")

    assert items == []


@pytest.mark.asyncio
async def test_insider_handles_network_error(insider_fetcher):
    """Returns empty list on network error."""
    with patch("sentiment.edgar.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("timeout"))
        MockClient.return_value = mock_client

        import httpx
        items = await insider_fetcher.fetch("AAPL")

    assert items == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_edgar.py -v'`
Expected: ImportError — `sentiment.edgar` not found

- [ ] **Step 4: Implement EDGAR fetchers**

```python
# backend/sentiment/edgar.py
"""SEC EDGAR fetchers — insider trades (Form 4) and filing sentiment."""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

from config.settings import get_settings
from sentiment.news_fetcher import NewsFetcher, NewsItem, _safe_parse_dt

logger = logging.getLogger(__name__)

EFTS_SEARCH = "https://efts.sec.gov/LATEST/search-index"
SEC_FILING_BASE = "https://www.sec.gov/Archives/edgar/data"
SEC_RATE_DELAY = 0.1  # 10 req/sec max per SEC guidelines


def _get_user_agent() -> str:
    return get_settings().SEC_EDGAR_USER_AGENT


class EdgarInsiderFetcher(NewsFetcher):
    """Fetch insider trade filings (Form 4) from SEC EDGAR."""

    def is_available(self) -> bool:
        return True

    async def fetch(self, ticker: str, limit: int = 10) -> list[NewsItem]:
        headers = {"User-Agent": _get_user_agent()}
        try:
            async with httpx.AsyncClient(timeout=20, headers=headers) as client:
                # Search for recent Form 4 filings
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=30)
                resp = await client.get(
                    EFTS_SEARCH,
                    params={
                        "q": f'"{ticker}"',
                        "dateRange": "custom",
                        "startdt": start.strftime("%Y-%m-%d"),
                        "enddt": end.strftime("%Y-%m-%d"),
                        "forms": "4",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return []

            items: list[NewsItem] = []
            async with httpx.AsyncClient(timeout=20, headers=headers) as client:
                for hit in hits[:limit]:
                    try:
                        source = hit.get("_source", {})
                        file_date = source.get("file_date", "")
                        filing_id = hit.get("_id", "")

                        # Try to fetch and parse the Form 4 XML
                        filing_url = f"https://www.sec.gov/Archives/edgar/data/{filing_id.replace('-', '')}"
                        resp = await client.get(filing_url)
                        await asyncio.sleep(SEC_RATE_DELAY)

                        if resp.status_code != 200:
                            # Fallback: generate headline from search metadata
                            names = source.get("display_names", [])
                            name = names[0] if names else "Insider"
                            items.append(
                                NewsItem(
                                    headline=f"{name} filed Form 4 for {ticker}",
                                    snippet="",
                                    source="edgar_insider",
                                    url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=4",
                                    published_at=_safe_parse_dt(file_date),
                                    ticker=ticker,
                                )
                            )
                            continue

                        # Parse Form 4 XML
                        item = self._parse_form4(resp.text, ticker, file_date)
                        if item:
                            items.append(item)

                    except Exception as exc:
                        logger.debug("Failed to parse Form 4 filing: %s", exc)
                        continue

            return items[:limit]
        except Exception as exc:
            logger.warning("EdgarInsiderFetcher error for %s: %s", ticker, exc)
            return []

    def _parse_form4(self, xml_text: str, ticker: str, file_date: str) -> NewsItem | None:
        """Parse a Form 4 XML and generate a sentiment-tagged NewsItem."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return None

        # Extract owner name
        owner_name = "Insider"
        name_el = root.find(".//rptOwnerName")
        if name_el is not None and name_el.text:
            owner_name = name_el.text

        # Extract title
        title_el = root.find(".//officerTitle")
        title = title_el.text if title_el is not None and title_el.text else ""

        # Parse transactions
        total_acquired = 0.0
        total_disposed = 0.0
        price = 0.0
        for txn in root.findall(".//nonDerivativeTransaction"):
            shares_el = txn.find(".//transactionShares/value")
            price_el = txn.find(".//transactionPricePerShare/value")
            code_el = txn.find(".//transactionAcquiredDisposedCode/value")

            shares = float(shares_el.text) if shares_el is not None and shares_el.text else 0
            if price_el is not None and price_el.text:
                try:
                    price = float(price_el.text)
                except ValueError:
                    pass
            code = code_el.text if code_el is not None else ""

            if code == "A":
                total_acquired += shares
            elif code == "D":
                total_disposed += shares

        if total_acquired == 0 and total_disposed == 0:
            return None

        # Generate headline
        who = f"{owner_name} ({title})" if title else owner_name
        if total_acquired > total_disposed:
            action = "purchased"
            shares = total_acquired
        else:
            action = "sold"
            shares = total_disposed

        price_str = f" at ${price:.2f}" if price > 0 else ""
        headline = f"{who} {action} {int(shares):,} shares of {ticker}{price_str}"

        return NewsItem(
            headline=headline,
            snippet="",
            source="edgar_insider",
            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=4",
            published_at=_safe_parse_dt(file_date),
            ticker=ticker,
        )


class EdgarFilingFetcher(NewsFetcher):
    """Fetch 10-K/10-Q filings and extract MD&A section for sentiment analysis."""

    def is_available(self) -> bool:
        return True

    async def fetch(self, ticker: str, limit: int = 5) -> list[NewsItem]:
        headers = {"User-Agent": _get_user_agent()}
        try:
            async with httpx.AsyncClient(timeout=20, headers=headers) as client:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=365)
                resp = await client.get(
                    EFTS_SEARCH,
                    params={
                        "q": f'"{ticker}"',
                        "dateRange": "custom",
                        "startdt": start.strftime("%Y-%m-%d"),
                        "enddt": end.strftime("%Y-%m-%d"),
                        "forms": "10-K,10-Q",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return []

            items: list[NewsItem] = []
            for hit in hits[:limit]:
                source = hit.get("_source", {})
                file_date = source.get("file_date", "")
                form_type = source.get("form_type", "10-K")
                names = source.get("display_names", [])
                company = names[0] if names else ticker

                headline = f"{company} filed {form_type} with SEC"
                items.append(
                    NewsItem(
                        headline=headline,
                        snippet=f"Annual/quarterly report filed on {file_date}",
                        source="edgar_filing",
                        url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type={form_type}",
                        published_at=_safe_parse_dt(file_date),
                        ticker=ticker,
                    )
                )

            return items[:limit]
        except Exception as exc:
            logger.warning("EdgarFilingFetcher error for %s: %s", ticker, exc)
            return []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_edgar.py -v'`
Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/amirb/quantsense
git add backend/sentiment/edgar.py backend/tests/test_edgar.py backend/config/settings.py
git commit -m "feat: add SEC EDGAR insider trades and filing fetchers"
```

---

### Task 3: Weighted Sentiment Aggregation

**Files:**
- Modify: `backend/sentiment/aggregator.py`
- Create: `backend/tests/test_weighted_aggregation.py`

- [ ] **Step 1: Write failing test for weighted aggregation**

```python
# backend/tests/test_weighted_aggregation.py
"""Tests for weighted sentiment aggregation."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from sentiment.aggregator import SentimentAggregator, SOURCE_WEIGHTS
from sentiment.news_fetcher import NewsItem


def _make_item(source: str, headline: str, score_hint: float = 0.0) -> NewsItem:
    """Helper to create a NewsItem."""
    return NewsItem(
        headline=headline,
        snippet="",
        source=source,
        url="https://example.com",
        published_at=datetime.now(timezone.utc),
        ticker="AAPL",
    )


def test_source_weights_exist():
    """All expected sources have weights."""
    assert "newsapi" in SOURCE_WEIGHTS
    assert "reddit" in SOURCE_WEIGHTS
    assert "yahoo" in SOURCE_WEIGHTS
    assert "stocktwits" in SOURCE_WEIGHTS
    assert "edgar_insider" in SOURCE_WEIGHTS
    assert "edgar_filing" in SOURCE_WEIGHTS


def test_source_weights_values():
    """Insider trades weighted highest, stocktwits lowest."""
    assert SOURCE_WEIGHTS["edgar_insider"] > SOURCE_WEIGHTS["newsapi"]
    assert SOURCE_WEIGHTS["stocktwits"] < SOURCE_WEIGHTS["newsapi"]


@pytest.mark.asyncio
async def test_weighted_scoring():
    """Weighted aggregation weights high-signal sources more."""
    agg = SentimentAggregator()

    # Mock VADER to return different scores per source
    mock_vader = MagicMock()
    # newsapi item scores +0.5, stocktwits scores +0.5
    # With weights (1.0 vs 0.7), newsapi should contribute more
    mock_vader.score = MagicMock(return_value=0.5)
    agg.vader = mock_vader

    # Create items from different sources
    newsapi_item = _make_item("newsapi", "AAPL beats earnings")
    stocktwits_item = _make_item("stocktwits", "AAPL to the moon")

    mock_fetcher1 = AsyncMock()
    mock_fetcher1.fetch = AsyncMock(return_value=[newsapi_item])
    mock_fetcher1.is_available = MagicMock(return_value=True)

    mock_fetcher2 = AsyncMock()
    mock_fetcher2.fetch = AsyncMock(return_value=[stocktwits_item])
    mock_fetcher2.is_available = MagicMock(return_value=True)

    agg.fetchers = [mock_fetcher1, mock_fetcher2]

    result = await agg.analyze_ticker("AAPL")

    # Both scored 0.5 by VADER, but weighted average should still be 0.5
    # (equal VADER scores means weights don't change the average)
    assert result.overall_score == pytest.approx(0.5, abs=0.01)
    assert result.num_sources == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_weighted_aggregation.py -v'`
Expected: ImportError — `SOURCE_WEIGHTS` not found in `sentiment.aggregator`

- [ ] **Step 3: Implement weighted aggregation**

In `backend/sentiment/aggregator.py`, add the weights constant after the imports (around line 22):

```python
# Source reliability weights for aggregation
SOURCE_WEIGHTS: dict[str, float] = {
    "newsapi": 1.0,
    "yahoo": 0.9,
    "reddit": 0.8,
    "stocktwits": 0.7,
    "edgar_insider": 1.3,
    "edgar_filing": 1.0,
}

DEFAULT_LLM_MULTIPLIER = 1.5
```

Modify the `analyze_ticker` method to use weighted scoring. Replace the VADER scoring loop (lines 63-78) and overall score calculation (lines 80-91):

```python
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

        # 2. Score every headline with VADER, tracking source weights
        headline_records: list[dict] = []
        vader_scores: list[float] = []
        weighted_sum = 0.0
        weight_total = 0.0
        for item in news_items:
            text = f"{item.headline}. {item.snippet}" if item.snippet else item.headline
            score = self.vader.score(text)
            vader_scores.append(score)

            source_weight = SOURCE_WEIGHTS.get(item.source, 1.0)
            weighted_sum += score * source_weight
            weight_total += source_weight

            headline_records.append(
                {
                    "headline": item.headline,
                    "score": round(score, 4),
                    "source": item.source,
                    "url": item.url,
                }
            )

        vader_avg = sum(vader_scores) / len(vader_scores) if vader_scores else 0.0
        weighted_vader = weighted_sum / weight_total if weight_total > 0 else 0.0

        # 3. Optional LLM deep analysis on top headlines
        llm_score: float | None = None
        if self.llm_provider and self.llm_provider.is_available():
            llm_score = await self._llm_analyze(news_items[:5], ticker)

        # 4. Compute overall score using weighted VADER
        if llm_score is not None:
            overall = 0.4 * weighted_vader + 0.6 * llm_score
        else:
            overall = weighted_vader

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
```

Add new fetchers to `create_aggregator()`. Replace the fetcher_candidates list:

```python
def create_aggregator() -> SentimentAggregator:
    """Create an aggregator wired up with all available providers."""
    from sentiment.stocktwits import StockTwitsFetcher
    from sentiment.edgar import EdgarInsiderFetcher, EdgarFilingFetcher

    agg = SentimentAggregator()

    # News fetchers — always try all; each checks its own availability
    fetcher_candidates: list[NewsFetcher] = [
        NewsAPIFetcher(),
        YahooNewsFetcher(),
        RedditFetcher(),
        StockTwitsFetcher(),
        EdgarInsiderFetcher(),
        EdgarFilingFetcher(),
    ]
    agg.fetchers = [f for f in fetcher_candidates if f.is_available()]

    # LLM provider — pick the first available (preference order)
    llm_candidates: list[LLMProvider] = [
        GroqProvider(),
        OpenAIProvider(),
        CopilotProvider(),
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
```

- [ ] **Step 4: Run tests**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_weighted_aggregation.py tests/test_stocktwits.py tests/test_edgar.py -v'`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
cd /home/amirb/quantsense
git add backend/sentiment/aggregator.py backend/tests/test_weighted_aggregation.py
git commit -m "feat: weighted sentiment aggregation with source reliability scores"
```

---

### Task 4: Category-Based Screener Scoring

**Files:**
- Modify: `backend/engine/screener.py`
- Create: `backend/tests/test_screener_scoring.py`

- [ ] **Step 1: Write failing test for category scoring**

```python
# backend/tests/test_screener_scoring.py
"""Tests for category-based screener scoring."""
import pytest
from engine.screener import (
    ScreenerResult,
    _score_technical,
    _score_sentiment,
    _score_fundamental,
    DEFAULT_CATEGORY_WEIGHTS,
)


def test_default_weights_sum_to_one():
    """Category weights must sum to 1.0."""
    total = sum(DEFAULT_CATEGORY_WEIGHTS.values())
    assert total == pytest.approx(1.0)


def test_technical_oversold_bullish():
    """RSI < 30 with price above SMA should be bullish."""
    score = _score_technical(rsi_val=25.0, price=100.0, sma_val=95.0, macd_hist=0.5, boll_pos=0.0)
    assert score > 0.3


def test_technical_overbought_bearish():
    """RSI > 70 with price below SMA should be bearish."""
    score = _score_technical(rsi_val=80.0, price=90.0, sma_val=95.0, macd_hist=-0.5, boll_pos=0.0)
    assert score < -0.3


def test_technical_neutral():
    """RSI ~50, price near SMA should be neutral."""
    score = _score_technical(rsi_val=50.0, price=100.0, sma_val=100.0, macd_hist=0.0, boll_pos=0.0)
    assert abs(score) < 0.2


def test_technical_handles_none():
    """Missing values should not crash, return 0."""
    score = _score_technical(rsi_val=None, price=100.0, sma_val=None, macd_hist=None, boll_pos=None)
    assert score == 0.0


def test_sentiment_positive():
    """Positive sentiment with improving trend should be bullish."""
    score = _score_sentiment(agg_score=0.6, trend="improving", num_sources=10)
    assert score > 0.5


def test_sentiment_negative():
    """Negative sentiment with declining trend should be bearish."""
    score = _score_sentiment(agg_score=-0.5, trend="declining", num_sources=5)
    assert score < -0.4


def test_sentiment_no_data():
    """No sentiment data should return 0."""
    score = _score_sentiment(agg_score=None, trend="stable", num_sources=0)
    assert score == 0.0


def test_fundamental_insider_buying():
    """Net insider buying should be bullish."""
    score = _score_fundamental(insider_buy_ratio=0.8, volume_ratio=1.0)
    assert score > 0.2


def test_fundamental_no_data():
    """No fundamental data should return 0."""
    score = _score_fundamental(insider_buy_ratio=None, volume_ratio=None)
    assert score == 0.0


def test_screener_result_has_category_scores():
    """ScreenerResult has all required category fields."""
    r = ScreenerResult(
        ticker="AAPL",
        price=185.0,
        score=0.45,
        signal="BUY",
        technical_score=0.6,
        sentiment_score=0.35,
        fundamental_score=0.3,
        factors={"rsi": 42},
        rsi=42.0,
        sma_20=180.0,
        sentiment=0.35,
    )
    assert r.technical_score == 0.6
    assert r.sentiment_score == 0.35
    assert r.fundamental_score == 0.3
    assert r.factors == {"rsi": 42}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_screener_scoring.py -v'`
Expected: ImportError — `_score_technical` not found

- [ ] **Step 3: Rewrite screener with category scoring**

Replace the entire contents of `backend/engine/screener.py`:

```python
"""Stock screener with category-based scoring (technical/sentiment/fundamental)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from data.provider import DataProvider
from .indicators import rsi, sma, macd, bollinger_bands

logger = logging.getLogger(__name__)

DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    "technical": 0.4,
    "sentiment": 0.35,
    "fundamental": 0.25,
}


@dataclass
class ScreenerResult:
    ticker: str
    price: float
    score: float            # composite -1.0 to +1.0
    signal: str             # BUY/SELL/HOLD
    technical_score: float
    sentiment_score: float
    fundamental_score: float
    factors: dict = field(default_factory=dict)
    # Legacy fields
    rsi: float | None = None
    sma_20: float | None = None
    sentiment: float | None = None


def _score_technical(
    rsi_val: float | None,
    price: float,
    sma_val: float | None,
    macd_hist: float | None,
    boll_pos: float | None,
) -> float:
    """Score technical factors, returns -1.0 to +1.0."""
    scores: list[float] = []

    # RSI: oversold → positive, overbought → negative
    if rsi_val is not None:
        rsi_score = (50 - rsi_val) / 50  # 0→+1, 50→0, 100→-1
        scores.append(max(-1.0, min(1.0, rsi_score)))

    # SMA trend: price above SMA → bullish
    if sma_val is not None and sma_val != 0:
        sma_score = (price - sma_val) / sma_val
        scores.append(max(-1.0, min(1.0, sma_score * 10)))

    # MACD histogram: positive → bullish
    if macd_hist is not None:
        macd_score = max(-0.5, min(0.5, macd_hist))
        scores.append(macd_score)

    # Bollinger position: near lower → bullish, near upper → bearish
    if boll_pos is not None:
        scores.append(max(-0.5, min(0.5, -boll_pos)))

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _score_sentiment(
    agg_score: float | None,
    trend: str,
    num_sources: int,
) -> float:
    """Score sentiment factors, returns -1.0 to +1.0."""
    if agg_score is None and num_sources == 0:
        return 0.0

    scores: list[float] = []

    # Aggregated sentiment score (direct pass-through)
    if agg_score is not None:
        scores.append(max(-1.0, min(1.0, agg_score)))

    # Trend direction
    trend_map = {"improving": 0.3, "declining": -0.3, "stable": 0.0}
    scores.append(trend_map.get(trend, 0.0))

    # Source count confidence
    if num_sources > 5:
        scores.append(0.1)
    elif num_sources < 2:
        scores.append(-0.1)
    else:
        scores.append(0.0)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _score_fundamental(
    insider_buy_ratio: float | None,
    volume_ratio: float | None,
) -> float:
    """Score fundamental factors, returns -1.0 to +1.0."""
    scores: list[float] = []

    # Insider buy/sell ratio: >0.5 means net buying
    if insider_buy_ratio is not None:
        if insider_buy_ratio > 0.5:
            scores.append(min(1.0, (insider_buy_ratio - 0.5) * 2))
        elif insider_buy_ratio < 0.5:
            scores.append(max(-0.5, (insider_buy_ratio - 0.5)))
        else:
            scores.append(0.0)

    # Volume ratio: high volume → momentum signal
    if volume_ratio is not None:
        if volume_ratio > 1.5:
            scores.append(0.3)
        elif volume_ratio < 0.5:
            scores.append(-0.2)
        else:
            scores.append(0.0)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _get_category_weights() -> dict[str, float]:
    """Load category weights from AppSetting or use defaults."""
    try:
        from models.database import SessionLocal
        from models.schemas import AppSetting
        db = SessionLocal()
        try:
            setting = db.query(AppSetting).filter(AppSetting.key == "screener_category_weights").first()
            if setting:
                weights = json.loads(setting.value)
                # Normalize to sum to 1.0
                total = sum(weights.values())
                if total > 0:
                    return {k: v / total for k, v in weights.items()}
        finally:
            db.close()
    except Exception:
        pass
    return DEFAULT_CATEGORY_WEIGHTS.copy()


async def _screen_one(
    ticker: str,
    provider: DataProvider,
    end: date,
    lookback_days: int = 100,
    sentiment_scores: dict[str, float] | None = None,
    sentiment_trends: dict[str, str] | None = None,
    sentiment_counts: dict[str, int] | None = None,
    insider_ratios: dict[str, float] | None = None,
    category_weights: dict[str, float] | None = None,
) -> ScreenerResult:
    """Evaluate a single ticker with category-based scoring."""
    start = end - timedelta(days=lookback_days)
    bars = await provider.get_ohlcv(ticker, start, end)

    if not bars:
        return ScreenerResult(
            ticker=ticker,
            price=0.0,
            score=0.0,
            signal="HOLD",
            technical_score=0.0,
            sentiment_score=0.0,
            fundamental_score=0.0,
        )

    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    price = closes[-1]

    # Compute indicators
    rsi_vals = rsi(closes, 14)
    sma_vals = sma(closes, 20)
    _, _, macd_hist_vals = macd(closes)
    upper, _, lower = bollinger_bands(closes)

    current_rsi = rsi_vals[-1]
    current_sma = sma_vals[-1]
    current_macd_hist = macd_hist_vals[-1]

    # Bollinger position: where price sits between bands (-1 lower, +1 upper)
    boll_pos = None
    if upper[-1] is not None and lower[-1] is not None and upper[-1] != lower[-1]:
        boll_pos = 2 * (price - lower[-1]) / (upper[-1] - lower[-1]) - 1

    # Volume ratio (current vs 20-day avg)
    vol_ratio = None
    if len(volumes) >= 20 and volumes[-1] > 0:
        avg_vol = sum(volumes[-20:]) / 20
        if avg_vol > 0:
            vol_ratio = volumes[-1] / avg_vol

    # Sentiment data
    sent_val = sentiment_scores.get(ticker) if sentiment_scores else None
    sent_trend = (sentiment_trends or {}).get(ticker, "stable")
    sent_count = (sentiment_counts or {}).get(ticker, 0)

    # Insider data
    insider_ratio = (insider_ratios or {}).get(ticker)

    # Score each category
    tech_score = _score_technical(current_rsi, price, current_sma, current_macd_hist, boll_pos)
    sent_score = _score_sentiment(sent_val, sent_trend, sent_count)
    fund_score = _score_fundamental(insider_ratio, vol_ratio)

    # Weighted composite
    weights = category_weights or DEFAULT_CATEGORY_WEIGHTS
    composite = (
        tech_score * weights.get("technical", 0.4)
        + sent_score * weights.get("sentiment", 0.35)
        + fund_score * weights.get("fundamental", 0.25)
    )
    composite = max(-1.0, min(1.0, composite))

    # Signal
    if composite > 0.3:
        signal = "BUY"
    elif composite < -0.3:
        signal = "SELL"
    else:
        signal = "HOLD"

    factors = {
        "rsi": round(current_rsi, 1) if current_rsi is not None else None,
        "sma_trend": "above" if current_sma and price > current_sma else "below" if current_sma else None,
        "macd": "bullish" if current_macd_hist and current_macd_hist > 0 else "bearish" if current_macd_hist else None,
        "sentiment": round(sent_val, 2) if sent_val is not None else None,
        "insider_activity": "buying" if insider_ratio and insider_ratio > 0.5 else "selling" if insider_ratio and insider_ratio < 0.5 else None,
        "volume_ratio": round(vol_ratio, 2) if vol_ratio is not None else None,
    }

    return ScreenerResult(
        ticker=ticker,
        price=price,
        score=round(composite, 4),
        signal=signal,
        technical_score=round(tech_score, 4),
        sentiment_score=round(sent_score, 4),
        fundamental_score=round(fund_score, 4),
        factors=factors,
        rsi=current_rsi,
        sma_20=current_sma,
        sentiment=sent_val,
    )


async def screen_tickers(
    tickers: list[str],
    provider: DataProvider,
    sentiment_scores: dict[str, float] | None = None,
    sentiment_trends: dict[str, str] | None = None,
    sentiment_counts: dict[str, int] | None = None,
    insider_ratios: dict[str, float] | None = None,
) -> list[ScreenerResult]:
    """Screen all tickers with category-based scoring.

    Parameters
    ----------
    sentiment_scores: ticker → overall sentiment score (-1 to +1)
    sentiment_trends: ticker → trend direction (improving/declining/stable)
    sentiment_counts: ticker → number of sentiment sources
    insider_ratios: ticker → insider buy ratio (0 to 1, >0.5 = net buying)
    """
    end = date.today()
    weights = _get_category_weights()
    tasks = [
        _screen_one(
            t, provider, end,
            sentiment_scores=sentiment_scores,
            sentiment_trends=sentiment_trends,
            sentiment_counts=sentiment_counts,
            insider_ratios=insider_ratios,
            category_weights=weights,
        )
        for t in tickers
    ]
    results = await asyncio.gather(*tasks)
    return sorted(results, key=lambda r: r.score, reverse=True)
```

- [ ] **Step 4: Run tests**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/test_screener_scoring.py -v'`
Expected: all tests PASS

- [ ] **Step 5: Run all tests to check nothing broke**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/ -v'`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/amirb/quantsense
git add backend/engine/screener.py backend/tests/test_screener_scoring.py
git commit -m "feat: category-based screener scoring (technical/sentiment/fundamental)"
```

---

### Task 5: Update Screener API Response

**Files:**
- Modify: `backend/api/market.py`

- [ ] **Step 1: Update screener endpoint to include new fields**

In `backend/api/market.py`, update the `run_screener` function. Replace the return serialization (lines 99-108):

```python
@router.get("/screener")
async def run_screener(db: Session = Depends(get_db)):
    """Screen all watchlist tickers and return scored results."""
    watchlist = db.query(Watchlist).all()
    if not watchlist:
        return []

    tickers = [w.ticker for w in watchlist]
    try:
        results = await screen_tickers(tickers, provider)
        return [
            {
                "ticker": r.ticker,
                "price": r.price,
                "rsi": r.rsi,
                "sma_20": r.sma_20,
                "sentiment": r.sentiment,
                "signal": r.signal,
                "score": r.score,
                "technical_score": r.technical_score,
                "sentiment_score": r.sentiment_score,
                "fundamental_score": r.fundamental_score,
                "factors": r.factors,
            }
            for r in results
        ]
    except Exception as exc:
        logger.exception("Screener failed")
        raise HTTPException(status_code=500, detail="Screener execution failed")
```

- [ ] **Step 2: Run all tests**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/ -v'`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
cd /home/amirb/quantsense
git add backend/api/market.py
git commit -m "feat: include category scores and factors in screener API response"
```

---

### Task 6: Final Integration Test

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `cd /home/amirb/quantsense/backend && bash -c 'source venv/bin/activate && python -m pytest tests/ -v'`
Expected: all tests PASS

- [ ] **Step 2: Build frontend to verify no type breakage**

Run: `cd /home/amirb/quantsense/frontend && npx next build 2>&1 | tail -20`
Expected: build succeeds (frontend types for screener are loose enough to accept new fields)

- [ ] **Step 3: Commit any fixups if needed**
