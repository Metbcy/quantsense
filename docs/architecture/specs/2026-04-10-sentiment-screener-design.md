# Backend Features — Sentiment Sources + Smart Screener Design Spec

**Date:** 2026-04-10
**Scope:** Add StockTwits + SEC EDGAR sentiment sources, weighted aggregation, category-based screener scoring

---

## 1. StockTwits Integration

### New File: `backend/sentiment/stocktwits.py`

Implements the `NewsFetcher` interface pattern used by `NewsAPIFetcher`, `RedditFetcher`, and `YahooNewsFetcher`.

**API:** `GET https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json`
- Unauthenticated, rate limit: 200 requests/hour
- Returns messages with optional `entities.sentiment.basic` field ("Bullish"/"Bearish")

**Data extraction per message:**
- `headline`: message body text (truncated to 500 chars)
- `source`: "stocktwits"
- `url`: link to message
- `published_at`: message creation timestamp
- `native_sentiment`: StockTwits' own bullish/bearish label (used as supplementary signal)

**Integration with existing pipeline:**
- Returns `list[NewsItem]` like other fetchers
- VADER scores each message
- LLM enrichment runs on same path as other sources
- StockTwits' native sentiment label stored in `snippet` field for reference

**Error handling:**
- 429 rate limit → log warning, return empty list, skip ticker
- Network errors → retry via existing `retry_async` decorator
- No API key required

---

## 2. SEC EDGAR Integration

### New File: `backend/sentiment/edgar.py`

Two distinct data types from EDGAR:

### 2a. Insider Trades (Form 4)

**API:** `GET https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={start}&enddt={end}&forms=4`

Alternative: `GET https://data.sec.gov/submissions/CIK{cik}.json` for recent filings.

**Data extraction:**
- Parse Form 4 XML for: insider name, title, transaction type (purchase/sale/gift), shares, price
- Generate a synthetic headline: "CEO John Smith purchased 10,000 shares at $185.50"
- Source: "edgar_insider"
- Sentiment mapping: purchase → +0.6, sale → -0.3 (insiders sell for many non-bearish reasons), gift → 0.0

**Note:** SEC requires `User-Agent` header with app name and contact email. Configure via settings: `SEC_EDGAR_USER_AGENT` env var, default `"QuantSense/1.0 (quantsense@example.com)"`.

### 2b. Filing Sentiment (10-K/10-Q)

**API:** Same EDGAR search, forms=10-K,10-Q

**Data extraction:**
- Fetch filing index page, locate "Management's Discussion and Analysis" section
- Extract first 2000 characters of MD&A text
- Run through VADER + LLM pipeline (same as news articles)
- Source: "edgar_filing"

**Rate limiting:**
- SEC asks for max 10 requests/second
- Add 0.1s delay between requests via `asyncio.sleep(0.1)`

**Error handling:**
- Filing parsing failures → log warning, skip filing, don't fail entire ticker
- CIK lookup failures → cache ticker→CIK mapping in memory, retry once

---

## 3. Weighted Sentiment Aggregation

### Modify: `backend/sentiment/aggregator.py`

Current behavior: all sources weighted equally when computing `overall_score`.

New behavior: weight by source reliability.

**Default weights:**

| Source | Weight | Rationale |
|--------|--------|-----------|
| newsapi | 1.0 | Baseline — professional journalism |
| reddit | 0.8 | Lower signal-to-noise than news |
| yahoo | 0.9 | Decent quality, some noise |
| stocktwits | 0.7 | High noise, but volume gives signal |
| edgar_insider | 1.3 | High signal — insiders have information |
| edgar_filing | 1.0 | Formal, reliable, but lagging |

**Implementation:**
- Store default weights as a dict constant in aggregator
- Allow override via `AppSetting` (key: `sentiment_source_weights`, value: JSON string)
- Weighted average formula: `sum(score * weight) / sum(weights)` for sources that returned data
- If a source returns no data for a ticker, it's excluded from the average (not counted as zero)

**LLM weight multiplier:**
- When LLM enrichment is available, LLM-scored items get 1.5x weight vs VADER-only
- This multiplier applies on top of source weight

---

## 4. Category-Based Screener Scoring

### Modify: `backend/engine/screener.py`

Replace single composite score with three-category scoring.

### Categories and Factors

**Technical (default weight: 40%)**

| Factor | Score Mapping |
|--------|--------------|
| RSI | <30 → +1.0 (oversold), >70 → -1.0 (overbought), 30-70 → linear 0 |
| SMA trend | price > SMA20 → +0.5, price < SMA20 → -0.5 |
| MACD histogram | positive → +0.5, negative → -0.5, scaled by magnitude |
| Bollinger position | near lower band → +0.5, near upper → -0.5 |

**Sentiment (default weight: 35%)**

| Factor | Score Mapping |
|--------|--------------|
| Aggregated score | pass through (-1.0 to +1.0) |
| Trend direction | improving → +0.3, declining → -0.3, stable → 0 |
| Source count | >5 sources → confidence boost +0.1, <2 → penalty -0.1 |

**Fundamental (default weight: 25%)**

| Factor | Score Mapping |
|--------|--------------|
| Insider buy/sell ratio | net buying → +0.5 to +1.0, net selling → -0.3, no activity → 0 |
| Volume ratio | current vol / 20-day avg vol; >1.5 → +0.3, <0.5 → -0.2 |

### Scoring Flow

1. Each factor normalized to -1.0 to +1.0
2. Factors averaged within category → category score (-1.0 to +1.0)
3. Category scores multiplied by weights → composite score
4. Signal: composite > 0.3 → "BUY", < -0.3 → "SELL", else "HOLD"

### Configurable Weights

- Default weights stored as constant: `{"technical": 0.4, "sentiment": 0.35, "fundamental": 0.25}`
- User overrides via `AppSetting` (key: `screener_category_weights`, value: JSON string)
- Weights must sum to 1.0 — normalize if they don't

### Updated ScreenerResult

```python
@dataclass
class ScreenerResult:
    ticker: str
    price: float
    score: float          # composite -1.0 to +1.0
    signal: str           # BUY/SELL/HOLD
    technical_score: float
    sentiment_score: float
    fundamental_score: float
    factors: dict         # individual factor values for display
    # Legacy fields kept for backwards compat
    rsi: float | None
    sma_20: float | None
    sentiment: float | None
```

---

## 5. API Changes

### Modify: `backend/api/market.py`

Update screener endpoint response to include category scores and factors breakdown. The `ScreenerResult` dataclass change handles this — just serialize the new fields.

### Modify: `backend/api/settings.py`

Add two new config keys readable/writable via existing config endpoints:
- `sentiment_source_weights` — JSON dict of source → weight
- `screener_category_weights` — JSON dict of category → weight

No new endpoints needed — existing `GET/PUT /api/settings/config` handles arbitrary key-value pairs.

---

## 6. Scheduler Changes

### Modify: `backend/sentiment/scheduler.py`

Add StockTwits and EDGAR to the refresh cycle. In `_refresh_watchlist_sentiment`:
- The `create_aggregator()` call already wires up fetchers
- Just add `StockTwitsFetcher` and `EdgarFetcher` to the fetcher list in `create_aggregator()`

### Modify: `backend/sentiment/aggregator.py` → `create_aggregator()`

Add new fetchers to the fetcher list:

```python
fetchers = [
    NewsAPIFetcher(...),
    RedditFetcher(...),
    YahooNewsFetcher(),
    StockTwitsFetcher(),      # NEW
    EdgarInsiderFetcher(),    # NEW
    EdgarFilingFetcher(),     # NEW
]
```

---

## 7. File Changes Summary

| File | Action |
|------|--------|
| `backend/sentiment/stocktwits.py` | **New** — StockTwits fetcher |
| `backend/sentiment/edgar.py` | **New** — SEC EDGAR insider + filing fetchers |
| `backend/sentiment/aggregator.py` | Modify — weighted scoring, new fetchers in `create_aggregator()` |
| `backend/sentiment/scheduler.py` | Modify — minimal (aggregator handles new sources) |
| `backend/engine/screener.py` | Modify — category-based scoring, updated `ScreenerResult` |
| `backend/api/market.py` | Modify — serialize new screener fields |
| `backend/tests/test_stocktwits.py` | **New** — StockTwits fetcher tests |
| `backend/tests/test_edgar.py` | **New** — EDGAR fetcher tests |
| `backend/tests/test_screener_scoring.py` | **New** — category scoring tests |

---

## 8. Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `SEC_EDGAR_USER_AGENT` | No | `QuantSense/1.0 (quantsense@example.com)` |

No new API keys required — both StockTwits and EDGAR are free/unauthenticated.

---

## 9. Out of Scope

- Frontend screener UI changes (weight sliders, score breakdown cards)
- Twitter/X integration
- Real-time StockTwits WebSocket streaming
- Full SEC filing NLP beyond MD&A section
- Crypto/forex sentiment sources
- Historical insider trade database (only recent filings)
