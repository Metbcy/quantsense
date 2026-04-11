# Dashboard UX Overhaul — Design Spec

**Date:** 2026-04-10
**Scope:** Real portfolio history tracking, recent trades card, watchlist widget on dashboard

---

## 1. Portfolio Snapshots (Backend)

### New DB Table: `portfolio_snapshots`

```sql
CREATE TABLE portfolio_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id),
    total_value FLOAT NOT NULL,
    cash        FLOAT NOT NULL,
    positions_value FLOAT NOT NULL,
    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_portfolio_snapshots_recorded_at ON portfolio_snapshots(portfolio_id, recorded_at);
```

- **Frequency:** Hourly, via asyncio background task in `lifespan`
- **Retention:** Keep all data (SQLite handles millions of rows fine for single-user app)
- **Snapshot logic:** Query current portfolio value using latest prices, insert row

### SQLAlchemy Model

Add `PortfolioSnapshot` to `models/schemas.py`:
- `id`, `portfolio_id` (FK → portfolios), `total_value`, `cash`, `positions_value`, `recorded_at`

### Background Task

In `main.py` lifespan, start an asyncio task that:
1. Runs every 60 minutes
2. Loads active portfolio + current prices
3. Inserts a `PortfolioSnapshot` row
4. Also takes a snapshot on every trade execution (already partially done in `PaperBroker._snapshot_portfolio_value` — wire this to DB instead of in-memory list)

### API Endpoint

`GET /api/portfolio/history?period=1W|1M|3M|1Y|all`

- Query `portfolio_snapshots` filtered by `recorded_at >= (now - period)`
- Downsample to max 200 points using SQL (take every Nth row via `ROW_NUMBER()` or Python-side stride)
- Response: `{ points: [{ timestamp: str, total_value: float, cash: float }] }`

---

## 2. Trade History Endpoint (Backend)

`GET /api/trading/history?limit=10&offset=0`

- Query existing `trades` table, ordered by `created_at DESC`
- Already have `Trade` model with: ticker, side, price, quantity, value, status, created_at
- Need to add `realized_pnl` column to `Trade` model (paper_broker already computes this but doesn't persist it)
- Response: `PaginatedResponse<Trade>`

### Schema Change

Add to `Trade` model:
- `realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)`

Alembic migration required.

---

## 3. Dashboard Frontend Changes

### 3a. Portfolio Chart — Real Data

**File:** `frontend/src/app/dashboard/page.tsx`

- Remove `generateMockHistory()` function
- Add timeframe selector: `1W | 1M | 3M | 1Y | All` (button group above chart)
- Fetch from `GET /api/portfolio/history?period={selected}`
- Keep existing AreaChart + gradient styling
- Show "No history yet" placeholder if < 2 data points

**New API function in `lib/api.ts`:**
```typescript
interface PortfolioHistoryPoint {
  timestamp: string;
  total_value: number;
  cash: number;
}

portfolio.history(period: string): Promise<{ points: PortfolioHistoryPoint[] }>
```

### 3b. Recent Trades Card

**Location:** Bottom row of dashboard, between Holdings and Screener (3-column grid)

- Fetch from `GET /api/trading/history?limit=10`
- Show: ticker, side (buy/sell badge), qty, price, realized P&L, timestamp
- Buy = green badge, Sell = red badge
- P&L colored green/red
- "No trades yet" empty state with icon

**New API function:**
```typescript
trading.history(limit?: number, offset?: number): Promise<PaginatedResponse<Trade>>
```

### 3c. Watchlist Widget

**Location:** After screener signals card, or replace screener if grid gets crowded. Keep as separate card.

- Reuse existing `useWatchlist` hook from `lib/hooks.ts`
- Show: ticker, current price, daily change %, add/remove button
- Fetch live prices via existing `api.market.quote()` for each ticker
- Compact layout — no sparklines (keep simple first iteration)
- "Add symbols to your watchlist" empty state

---

## 4. Dashboard Layout

Current: 4 stat cards → chart → 2-column (holdings + screener)

New: 4 stat cards → chart with timeframe selector → 3-column (holdings + recent trades + screener) → watchlist card (full width or alongside)

Grid breakpoints:
- Desktop (lg+): 3 columns for middle row
- Tablet (md): 2 columns, trades below
- Mobile: single column stack

---

## 5. File Changes Summary

| File | Action |
|------|--------|
| `backend/models/schemas.py` | Add `PortfolioSnapshot` model, add `realized_pnl` to `Trade` |
| `backend/models/database.py` | Add `PortfolioSnapshot` to `init_db` imports |
| `backend/api/trading.py` | Add `GET /history` endpoint, persist `realized_pnl` on trades |
| `backend/api/portfolio_history.py` | **New** — history endpoint with period filtering + downsampling |
| `backend/main.py` | Register portfolio_history router, add hourly snapshot background task |
| `backend/trading/paper_broker.py` | Wire `_snapshot_portfolio_value` to DB instead of in-memory list |
| `backend/alembic/versions/xxx_add_snapshots.py` | **New** — migration for snapshot table + realized_pnl column |
| `frontend/src/lib/api.ts` | Add `portfolio.history()` and `trading.history()` API functions |
| `frontend/src/app/dashboard/page.tsx` | Replace mock chart, add timeframe selector, add trades card, add watchlist widget |

---

## 6. Out of Scope

- Real-time WebSocket push for portfolio value (poll on page load is sufficient)
- Sparklines in watchlist (future enhancement)
- Portfolio history export/CSV
- Multiple portfolio support (use default portfolio only)
