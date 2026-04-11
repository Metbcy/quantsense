# Dashboard UX Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mock portfolio chart with real DB-backed history, add recent trades card and watchlist widget to dashboard.

**Architecture:** New `PortfolioSnapshot` model stores hourly portfolio values. Background asyncio task captures snapshots. New API endpoint serves history with period filtering. Frontend dashboard consumes real data and adds two new cards.

**Tech Stack:** SQLAlchemy, Alembic, FastAPI, asyncio, Next.js, Recharts, shadcn/ui

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/models/schemas.py` | Modify | Add `PortfolioSnapshot` model |
| `backend/models/database.py` | Modify | Import `PortfolioSnapshot` in `init_db` |
| `backend/api/portfolio_history.py` | Create | `/api/portfolio/history` endpoint |
| `backend/main.py` | Modify | Register router, start hourly snapshot task |
| `backend/tests/test_portfolio_snapshots.py` | Create | Tests for snapshot model + history endpoint |
| `backend/alembic/versions/add_portfolio_snapshots.py` | Create | Migration for new table |
| `frontend/src/lib/api.ts` | Modify | Add `PortfolioHistoryPoint` type + `portfolio.history()` |
| `frontend/src/app/dashboard/page.tsx` | Modify | Real chart, trades card, watchlist widget |

---

### Task 1: PortfolioSnapshot Model

**Files:**
- Modify: `backend/models/schemas.py`
- Modify: `backend/models/database.py`
- Create: `backend/tests/test_portfolio_snapshots.py`

- [ ] **Step 1: Write failing test for PortfolioSnapshot creation**

```python
# backend/tests/test_portfolio_snapshots.py
"""Tests for portfolio snapshot persistence."""
import pytest
from datetime import datetime
from models.schemas import Portfolio as PortfolioDB, PortfolioSnapshot


def test_create_snapshot(db_session):
    """Snapshot can be created and queried."""
    portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
    db_session.add(portfolio)
    db_session.commit()

    snap = PortfolioSnapshot(
        portfolio_id=portfolio.id,
        total_value=105000.0,
        cash=50000.0,
        positions_value=55000.0,
        recorded_at=datetime(2026, 4, 10, 12, 0, 0),
    )
    db_session.add(snap)
    db_session.commit()

    result = db_session.query(PortfolioSnapshot).filter_by(portfolio_id=portfolio.id).first()
    assert result is not None
    assert result.total_value == 105000.0
    assert result.cash == 50000.0
    assert result.positions_value == 55000.0


def test_snapshots_ordered_by_time(db_session):
    """Multiple snapshots returned in chronological order."""
    portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
    db_session.add(portfolio)
    db_session.commit()

    for i, val in enumerate([100000, 101000, 99500]):
        snap = PortfolioSnapshot(
            portfolio_id=portfolio.id,
            total_value=val,
            cash=50000.0,
            positions_value=val - 50000.0,
            recorded_at=datetime(2026, 4, 10, 10 + i, 0, 0),
        )
        db_session.add(snap)
    db_session.commit()

    snaps = (
        db_session.query(PortfolioSnapshot)
        .filter_by(portfolio_id=portfolio.id)
        .order_by(PortfolioSnapshot.recorded_at.asc())
        .all()
    )
    assert len(snaps) == 3
    assert snaps[0].total_value == 100000
    assert snaps[2].total_value == 99500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/amirb/quantsense/backend && python -m pytest tests/test_portfolio_snapshots.py -v`
Expected: ImportError — `PortfolioSnapshot` not found

- [ ] **Step 3: Add PortfolioSnapshot model to schemas.py**

Add after the `Trade` class in `backend/models/schemas.py`:

```python
class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portfolio_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("portfolios.id"), nullable=False, index=True
    )
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    positions_value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True)

    portfolio: Mapped["Portfolio"] = relationship()
```

- [ ] **Step 4: Add PortfolioSnapshot import to init_db in database.py**

In `backend/models/database.py`, add `PortfolioSnapshot` to the imports in `init_db()`:

```python
def init_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    from models.schemas import (  # noqa: F401
        User,
        Watchlist,
        OHLCVData,
        SentimentRecord,
        SentimentAggregate,
        Strategy,
        BacktestResult,
        BacktestTrade,
        Portfolio,
        Position,
        Trade,
        AppSetting,
        PortfolioSnapshot,
    )
    Base.metadata.create_all(bind=engine)
    _db_initialized = True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/amirb/quantsense/backend && python -m pytest tests/test_portfolio_snapshots.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/amirb/quantsense
git add backend/models/schemas.py backend/models/database.py backend/tests/test_portfolio_snapshots.py
git commit -m "feat: add PortfolioSnapshot model for portfolio history tracking"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/add_portfolio_snapshots.py`

- [ ] **Step 1: Generate alembic migration**

Run: `cd /home/amirb/quantsense/backend && python -m alembic revision --autogenerate -m "add portfolio_snapshots table"`

- [ ] **Step 2: Verify generated migration contains correct table creation**

Check the generated file has `op.create_table('portfolio_snapshots', ...)` with columns: id, portfolio_id, total_value, cash, positions_value, recorded_at, and indexes on portfolio_id and recorded_at.

- [ ] **Step 3: Run migration**

Run: `cd /home/amirb/quantsense/backend && python -m alembic upgrade head`
Expected: migration applies successfully

- [ ] **Step 4: Commit**

```bash
cd /home/amirb/quantsense
git add backend/alembic/versions/
git commit -m "chore: alembic migration for portfolio_snapshots table"
```

---

### Task 3: Portfolio History API Endpoint

**Files:**
- Create: `backend/api/portfolio_history.py`
- Modify: `backend/main.py`
- Modify: `backend/tests/test_portfolio_snapshots.py`

- [ ] **Step 1: Write failing test for history endpoint**

Append to `backend/tests/test_portfolio_snapshots.py`:

```python
from datetime import timedelta
from fastapi.testclient import TestClient


def _create_app_with_db(db_session):
    """Create a minimal FastAPI app wired to test DB."""
    from fastapi import FastAPI, Depends
    from api.portfolio_history import router

    app = FastAPI()

    def override_db():
        yield db_session

    app.include_router(router, prefix="/api/portfolio")
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_history_endpoint_returns_points(db_session):
    """GET /api/portfolio/history returns snapshot points filtered by period."""
    from models.database import get_db

    portfolio = PortfolioDB(name="default", cash=100000.0, initial_cash=100000.0)
    db_session.add(portfolio)
    db_session.commit()

    now = datetime.utcnow()
    for i in range(48):  # 48 hours of snapshots
        snap = PortfolioSnapshot(
            portfolio_id=portfolio.id,
            total_value=100000 + i * 100,
            cash=50000.0,
            positions_value=50000 + i * 100,
            recorded_at=now - timedelta(hours=48 - i),
        )
        db_session.add(snap)
    db_session.commit()

    from fastapi import FastAPI, Depends
    from api.portfolio_history import router

    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    # Mount router
    app.include_router(router, prefix="/api/portfolio")

    # 1W should return all 48 points (all within 1 week)
    res = client.get("/api/portfolio/history?period=1W")
    assert res.status_code == 200
    data = res.json()
    assert "points" in data
    assert len(data["points"]) == 48

    # 1M should also return all 48
    res = client.get("/api/portfolio/history?period=1M")
    assert res.status_code == 200
    assert len(res.json()["points"]) == 48
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/amirb/quantsense/backend && python -m pytest tests/test_portfolio_snapshots.py::test_history_endpoint_returns_points -v`
Expected: ImportError — `api.portfolio_history` not found

- [ ] **Step 3: Create portfolio_history.py endpoint**

```python
# backend/api/portfolio_history.py
"""Portfolio history endpoint — serves time-series of portfolio snapshots."""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from models.database import get_db
from models.schemas import Portfolio as PortfolioDB, PortfolioSnapshot

logger = logging.getLogger(__name__)

router = APIRouter()

PERIOD_DELTAS = {
    "1W": timedelta(weeks=1),
    "1M": timedelta(days=30),
    "3M": timedelta(days=90),
    "1Y": timedelta(days=365),
}

MAX_POINTS = 200


@router.get("/history")
def get_portfolio_history(
    period: str = Query("1M", regex="^(1W|1M|3M|1Y|all)$"),
    db: Session = Depends(get_db),
):
    """Return portfolio value history for the given period."""
    portfolio = db.query(PortfolioDB).filter(PortfolioDB.name == "default").first()
    if not portfolio:
        return {"points": []}

    query = (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.portfolio_id == portfolio.id)
    )

    if period != "all":
        cutoff = datetime.utcnow() - PERIOD_DELTAS[period]
        query = query.filter(PortfolioSnapshot.recorded_at >= cutoff)

    query = query.order_by(PortfolioSnapshot.recorded_at.asc())
    snapshots = query.all()

    # Downsample if too many points
    if len(snapshots) > MAX_POINTS:
        stride = len(snapshots) / MAX_POINTS
        sampled = []
        for i in range(MAX_POINTS):
            idx = int(i * stride)
            sampled.append(snapshots[idx])
        # Always include last point
        if sampled[-1] != snapshots[-1]:
            sampled[-1] = snapshots[-1]
        snapshots = sampled

    return {
        "points": [
            {
                "timestamp": s.recorded_at.isoformat(),
                "total_value": s.total_value,
                "cash": s.cash,
            }
            for s in snapshots
        ]
    }
```

- [ ] **Step 4: Register router in main.py**

In `backend/main.py`, add import and router registration:

```python
# Add import near other router imports
from api.portfolio_history import router as portfolio_history_router

# Add in Routes section
app.include_router(portfolio_history_router, prefix="/api/portfolio", tags=["portfolio"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /home/amirb/quantsense/backend && python -m pytest tests/test_portfolio_snapshots.py -v`
Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /home/amirb/quantsense
git add backend/api/portfolio_history.py backend/main.py backend/tests/test_portfolio_snapshots.py
git commit -m "feat: add GET /api/portfolio/history endpoint with period filtering"
```

---

### Task 4: Hourly Snapshot Background Task

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add snapshot background task to lifespan**

In `backend/main.py`, add the snapshot task inside the `lifespan` context manager. Add these imports at the top:

```python
import asyncio
from models.schemas import Portfolio as PortfolioDB, PortfolioSnapshot, Position as PositionDB
```

Add this function before the `lifespan` function:

```python
async def _snapshot_loop():
    """Take a portfolio snapshot every hour."""
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            db = SessionLocal()
            try:
                portfolio = db.query(PortfolioDB).filter(PortfolioDB.name == "default").first()
                if portfolio:
                    positions = db.query(PositionDB).filter(PositionDB.portfolio_id == portfolio.id).all()
                    positions_value = sum(
                        p.current_price * p.quantity for p in positions if p.quantity > 0
                    )
                    total_value = portfolio.cash + positions_value
                    snap = PortfolioSnapshot(
                        portfolio_id=portfolio.id,
                        total_value=total_value,
                        cash=portfolio.cash,
                        positions_value=positions_value,
                    )
                    db.add(snap)
                    db.commit()
                    logger.info("Portfolio snapshot: $%.2f", total_value)
            finally:
                db.close()
        except Exception:
            logger.exception("Snapshot task failed")
```

Modify the `lifespan` function to start and cancel the task:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    logger.info("QuantSense API started")
    if settings.WEBHOOK_SECRET == "quantsense_secret_123":
        logger.warning(
            "WEBHOOK_SECRET is using the default placeholder — "
            "set a secure value via the WEBHOOK_SECRET env var"
        )
    from sentiment.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    snapshot_task = asyncio.create_task(_snapshot_loop())
    yield
    snapshot_task.cancel()
    stop_scheduler()
    logger.info("QuantSense API shutting down")
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

Run: `cd /home/amirb/quantsense/backend && python -m pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
cd /home/amirb/quantsense
git add backend/main.py
git commit -m "feat: add hourly portfolio snapshot background task"
```

---

### Task 5: Frontend — Portfolio History API + Types

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add PortfolioHistoryPoint type and portfolio.history() method**

In `frontend/src/lib/api.ts`, add the type after the `Portfolio` interface (~line 138):

```typescript
export interface PortfolioHistoryPoint {
  timestamp: string;
  total_value: number;
  cash: number;
}
```

Add a `portfolio` namespace to the `api` object, after the `trading` section (~line 484):

```typescript
  portfolio: {
    history: (period: string = '1M') =>
      fetchJson<{ points: PortfolioHistoryPoint[] }>(`/portfolio/history?period=${encodeURIComponent(period)}`),
  },
```

- [ ] **Step 2: Commit**

```bash
cd /home/amirb/quantsense
git add frontend/src/lib/api.ts
git commit -m "feat: add portfolio history API client"
```

---

### Task 6: Dashboard — Real Portfolio Chart with Timeframe Selector

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Replace mock chart with real data**

In `frontend/src/app/dashboard/page.tsx`:

1. Remove the `generateMockHistory` function (lines 38-55)
2. Add state for timeframe and history fetch
3. Replace chart data source

Add imports at top (add `useState` to existing react import):

```typescript
import { useState, useMemo } from "react";
```

Replace the chart section. After the `stats` array and before `return`, add:

```typescript
  const [period, setPeriod] = useState("1M");
  const {
    data: historyData,
    loading: historyLoading,
  } = useFetch<{ points: { timestamp: string; total_value: number; cash: number }[] }>(
    () => api.portfolio.history(period),
    [period]
  );

  const chartData = useMemo(() => {
    if (!historyData?.points?.length) return [];
    return historyData.points.map((p) => ({
      date: new Date(p.timestamp).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      }),
      value: p.total_value,
    }));
  }, [historyData]);
```

Remove the old `chartData` useMemo that calls `generateMockHistory`.

2. Add timeframe buttons inside the Portfolio Chart card, in `CardHeader`:

```tsx
<CardHeader className="flex flex-row items-center justify-between">
  <CardTitle className="text-zinc-100">Portfolio Value</CardTitle>
  <div className="flex gap-1">
    {["1W", "1M", "3M", "1Y", "All"].map((p) => (
      <button
        key={p}
        onClick={() => setPeriod(p.toLowerCase() === "all" ? "all" : p)}
        className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
          period === (p.toLowerCase() === "all" ? "all" : p)
            ? "bg-blue-600 text-white"
            : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
        }`}
      >
        {p}
      </button>
    ))}
  </div>
</CardHeader>
```

3. Add empty state inside chart `CardContent`, before the `ResponsiveContainer`:

```tsx
{chartData.length < 2 ? (
  <div className="flex h-[300px] items-center justify-center text-zinc-500">
    <div className="text-center">
      <Activity className="mx-auto mb-2 size-8" />
      <p className="text-sm">Portfolio history will appear here</p>
      <p className="text-xs text-zinc-600 mt-1">Snapshots are taken hourly</p>
    </div>
  </div>
) : (
  <div className="h-[300px] w-full">
    {/* existing ResponsiveContainer + AreaChart unchanged */}
  </div>
)}
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd /home/amirb/quantsense/frontend && npx next build 2>&1 | tail -20`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
cd /home/amirb/quantsense
git add frontend/src/app/dashboard/page.tsx
git commit -m "feat: replace mock portfolio chart with real history data + timeframe selector"
```

---

### Task 7: Dashboard — Recent Trades Card

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Add recent trades card to dashboard bottom row**

In `frontend/src/app/dashboard/page.tsx`, add a trades fetch near the existing hooks:

```typescript
const {
  data: tradesData,
  loading: tradesLoading,
} = useFetch<{ items: TradeRecord[]; total: number }>(
  () => api.trading.history(1, 10),
  []
);
```

Add `TradeRecord` to the import from `@/lib/api`:

```typescript
import type { ScreenerResult, TradeRecord } from "@/lib/api";
```

Change the bottom row grid from `lg:grid-cols-3` (it's currently a 2-col with `lg:col-span-2` on holdings). Update to 3 equal columns:

Change: `<div className="grid grid-cols-1 gap-6 lg:grid-cols-3">`

Change holdings card from `lg:col-span-2` to `lg:col-span-1`.

Add the Recent Trades card between Holdings and Screener:

```tsx
{/* Recent Trades */}
<Card className="border-zinc-800 bg-zinc-900">
  <CardHeader>
    <CardTitle className="text-zinc-100">Recent Trades</CardTitle>
  </CardHeader>
  <CardContent>
    {tradesLoading ? (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 animate-pulse rounded bg-zinc-800" />
        ))}
      </div>
    ) : !tradesData?.items?.length ? (
      <div className="flex flex-col items-center justify-center py-8 text-zinc-500">
        <Activity className="mb-2 size-6" />
        <p className="text-sm">No trades yet</p>
      </div>
    ) : (
      <div className="space-y-2">
        {tradesData.items.slice(0, 10).map((trade) => (
          <div
            key={trade.id}
            className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
          >
            <div className="flex items-center gap-2">
              <Badge
                className={
                  trade.side === "buy"
                    ? "bg-green-500/20 text-green-400"
                    : "bg-red-500/20 text-red-400"
                }
              >
                {trade.side.toUpperCase()}
              </Badge>
              <span className="font-mono font-semibold text-zinc-100">
                {trade.ticker}
              </span>
              <span className="text-xs text-zinc-500">
                {trade.quantity} @ ${trade.price.toFixed(2)}
              </span>
            </div>
            <span className="text-xs text-zinc-500">
              {trade.timestamp
                ? new Date(trade.timestamp).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })
                : ""}
            </span>
          </div>
        ))}
      </div>
    )}
  </CardContent>
</Card>
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd /home/amirb/quantsense/frontend && npx next build 2>&1 | tail -20`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
cd /home/amirb/quantsense
git add frontend/src/app/dashboard/page.tsx
git commit -m "feat: add recent trades card to dashboard"
```

---

### Task 8: Dashboard — Watchlist Widget

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Add watchlist card below the 3-column row**

Import the watchlist hook:

```typescript
import { usePortfolio, useFetch, useWatchlist } from "@/lib/hooks";
```

Add hook call near other hooks:

```typescript
const { watchlist, loading: watchlistLoading, remove: removeFromWatchlist } = useWatchlist();
```

Add `Star` and `X` to the lucide-react imports:

```typescript
import { ..., Star, X } from "lucide-react";
```

Add the watchlist card after the 3-column grid div:

```tsx
{/* Watchlist */}
<Card className="border-zinc-800 bg-zinc-900">
  <CardHeader>
    <CardTitle className="text-zinc-100 flex items-center gap-2">
      <Star className="size-4" />
      Watchlist
    </CardTitle>
  </CardHeader>
  <CardContent>
    {watchlistLoading ? (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 animate-pulse rounded bg-zinc-800" />
        ))}
      </div>
    ) : !watchlist?.length ? (
      <div className="flex flex-col items-center justify-center py-8 text-zinc-500">
        <Star className="mb-2 size-6" />
        <p className="text-sm">No watchlist items</p>
        <p className="text-xs text-zinc-600 mt-1">
          Add symbols from the Settings page
        </p>
      </div>
    ) : (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {watchlist.map((item) => (
          <div
            key={item.ticker}
            className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
          >
            <div>
              <span className="font-mono font-semibold text-zinc-100">
                {item.ticker}
              </span>
              {item.name && (
                <span className="ml-2 text-xs text-zinc-500 truncate max-w-[120px] inline-block align-middle">
                  {item.name}
                </span>
              )}
            </div>
            <button
              onClick={() => removeFromWatchlist(item.ticker)}
              className="text-zinc-600 hover:text-red-400 transition-colors"
              title="Remove from watchlist"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    )}
  </CardContent>
</Card>
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd /home/amirb/quantsense/frontend && npx next build 2>&1 | tail -20`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
cd /home/amirb/quantsense
git add frontend/src/app/dashboard/page.tsx
git commit -m "feat: add watchlist widget to dashboard"
```

---

### Task 9: Final Integration Test

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `cd /home/amirb/quantsense/backend && python -m pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 2: Run frontend build**

Run: `cd /home/amirb/quantsense/frontend && npx next build 2>&1 | tail -30`
Expected: build succeeds with no errors

- [ ] **Step 3: Final commit if any fixups needed**

Only if previous steps required fixes.
