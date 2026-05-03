import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { PortfolioBacktestRequest, PortfolioBacktestResult } from "@/lib/api";

// Sample backend response, shape-faithful to what
// `POST /api/backtest/portfolio` returns from `_serialize_result`
// in backend/api/backtest_portfolio.py.
const samplePortfolioResponse: PortfolioBacktestResult = {
  run_hash: "deadbeefcafebabe1234567890abcdef",
  config: {
    tickers: ["AAPL", "MSFT"],
    weights: null,
    start_date: "2020-01-01",
    end_date: "2020-12-31",
    initial_capital: 100000,
    rebalance_schedule: "monthly",
    slippage_bps: 5,
    commission_per_share: 0,
    commission_pct: 0,
    benchmark_ticker: "SPY",
    seed: 42,
  },
  metrics: {
    total_return_pct: 12.34,
    annualized_return_pct: 12.0,
    sharpe_ratio: 1.45,
    sortino_ratio: 1.9,
    calmar_ratio: 0.8,
    max_drawdown_pct: -15.2,
    max_drawdown_duration_bars: 30,
    downside_deviation: 0.01,
    alpha: 0.02,
    beta: 0.95,
    deflated_sharpe_ratio: 1.1,
  },
  equity_curve: [
    ["2020-01-02", 100000],
    ["2020-12-31", 112340],
  ],
  equity_curve_full_length: 252,
  equity_curve_returned_length: 2,
  final_cash: 1234.56,
  final_positions: { AAPL: 100, MSFT: 50 },
  total_turnover: 50000,
  per_ticker_pnl: {
    AAPL: { realized: 5000, unrealized: 1500 },
    MSFT: { realized: 4000, unrealized: 1834 },
  },
  fills: {
    AAPL: [
      {
        date: "2020-01-02",
        side: "buy",
        quantity: 100,
        fill_price: 75,
        notional: 7500,
        commission: 0,
        slippage_cost: 3.75,
        reason: "rebalance",
      },
    ],
    MSFT: [],
  },
  benchmark_equity_curve: [
    ["2020-01-02", 100],
    ["2020-12-31", 116],
  ],
};

describe("runPortfolioBacktest", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("qs_token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs to /api/backtest/portfolio with the request body and parses the response", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(samplePortfolioResponse),
    });
    vi.stubGlobal("fetch", mockFetch);

    // Re-import so the api module sees the stubbed fetch on first call.
    const { runPortfolioBacktest } = await import("@/lib/api");

    const req: PortfolioBacktestRequest = {
      tickers: ["AAPL", "MSFT"],
      weights: null,
      start_date: "2020-01-01",
      end_date: "2020-12-31",
      initial_capital: 100000,
      rebalance_schedule: "monthly",
      slippage_bps: 5,
      commission_per_share: 0,
      commission_pct: 0,
      benchmark_ticker: "SPY",
      seed: 42,
    };

    const result = await runPortfolioBacktest(req);

    // URL + method
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/backtest/portfolio");
    expect(options.method).toBe("POST");

    // Body round-trips correctly
    const sentBody = JSON.parse(options.body as string);
    expect(sentBody).toEqual(req);

    // Parsed result preserves shape
    expect(result.run_hash).toBe("deadbeefcafebabe1234567890abcdef");
    expect(result.metrics.sharpe_ratio).toBeCloseTo(1.45);
    expect(result.equity_curve).toHaveLength(2);
    expect(result.equity_curve[0]).toEqual(["2020-01-02", 100000]);
    expect(result.per_ticker_pnl.AAPL.realized).toBe(5000);
    expect(result.fills.AAPL).toHaveLength(1);
    expect(result.benchmark_equity_curve).toHaveLength(2);
  });

  it("propagates backend error detail on non-ok response", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ detail: "Duplicate tickers in request" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { runPortfolioBacktest } = await import("@/lib/api");

    await expect(
      runPortfolioBacktest({
        tickers: ["AAPL", "AAPL"],
        weights: null,
        start_date: "2020-01-01",
        end_date: "2020-12-31",
        initial_capital: 100000,
        rebalance_schedule: "monthly",
        slippage_bps: 5,
        commission_per_share: 0,
        commission_pct: 0,
        benchmark_ticker: null,
      }),
    ).rejects.toThrow("Duplicate tickers in request");
  });
});
