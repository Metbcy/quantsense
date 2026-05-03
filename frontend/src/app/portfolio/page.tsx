"use client";

import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Play } from "lucide-react";
import { toast } from "sonner";
import { format as fnsFormat } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DatePicker } from "@/components/ui/date-picker";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/ui/stat";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type {
  PortfolioBacktestRequest,
  PortfolioBacktestResult,
  RebalanceSchedule,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatCurrency(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(n);
}

function formatPct(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function defaultDates() {
  const end = new Date();
  const start = new Date();
  start.setFullYear(start.getFullYear() - 3);
  return { start, end };
}

function dateToStr(d: Date | undefined): string {
  return d ? fnsFormat(d, "yyyy-MM-dd") : "";
}

const REBALANCE_OPTIONS: { value: RebalanceSchedule; label: string }[] = [
  { value: "never", label: "Never" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
];

// Parse "AAPL, MSFT, GOOG" → ["AAPL","MSFT","GOOG"], deduped, uppercased.
function parseTickers(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(/[,\s]+/)
        .map((t) => t.trim().toUpperCase())
        .filter((t) => t.length > 0),
    ),
  );
}

// Parse weights like "0.4, 0.3, 0.3" or "0.4 0.3 0.3" → number[].
// Returns null if the input is empty (caller signals equal-weight).
function parseWeightsToList(raw: string): number[] | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  return trimmed
    .split(/[,\s]+/)
    .map((t) => Number(t.trim()))
    .filter((n) => !Number.isNaN(n));
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const dates = useMemo(defaultDates, []);

  const [tickersRaw, setTickersRaw] = useState("AAPL, MSFT, GOOG");
  const [weightsRaw, setWeightsRaw] = useState("");
  const [startDate, setStartDate] = useState<Date | undefined>(dates.start);
  const [endDate, setEndDate] = useState<Date | undefined>(dates.end);
  const [rebalance, setRebalance] = useState<RebalanceSchedule>("monthly");
  const [initialCapital, setInitialCapital] = useState(100000);
  const [slippageBps, setSlippageBps] = useState(5);
  const [commissionPerShare, setCommissionPerShare] = useState(0);
  const [commissionPct, setCommissionPct] = useState(0);
  const [benchmarkTicker, setBenchmarkTicker] = useState("SPY");
  const [seed, setSeed] = useState(42);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PortfolioBacktestResult | null>(null);

  const tickers = useMemo(() => parseTickers(tickersRaw), [tickersRaw]);
  const weightList = useMemo(() => parseWeightsToList(weightsRaw), [weightsRaw]);

  // Validator: equal-weight if blank; otherwise must be one number per ticker
  // and sum to 1.0 within a small tolerance.
  const weightHint = useMemo(() => {
    if (!weightList) return "Auto equal-weight across tickers.";
    if (weightList.length !== tickers.length) {
      return `Need ${tickers.length} weight${tickers.length === 1 ? "" : "s"}; got ${weightList.length}.`;
    }
    const sum = weightList.reduce((a, b) => a + b, 0);
    if (Math.abs(sum - 1) > 1e-3) {
      return `Weights sum to ${sum.toFixed(4)}; must sum to 1.0.`;
    }
    return `Sum = ${sum.toFixed(4)} ✓`;
  }, [weightList, tickers]);

  const weightsValid =
    !weightList ||
    (weightList.length === tickers.length &&
      Math.abs(weightList.reduce((a, b) => a + b, 0) - 1) <= 1e-3);

  async function handleRun() {
    if (tickers.length === 0) {
      toast.error("Enter at least one ticker");
      return;
    }
    if (!startDate || !endDate) {
      toast.error("Select start and end dates");
      return;
    }
    if (!weightsValid) {
      toast.error("Fix the weight inputs");
      return;
    }

    let weightsObj: Record<string, number> | null = null;
    if (weightList) {
      const obj: Record<string, number> = {};
      tickers.forEach((t, i) => {
        obj[t] = weightList[i];
      });
      weightsObj = obj;
    }

    const req: PortfolioBacktestRequest = {
      tickers,
      weights: weightsObj,
      start_date: dateToStr(startDate),
      end_date: dateToStr(endDate),
      initial_capital: initialCapital,
      rebalance_schedule: rebalance,
      slippage_bps: slippageBps,
      commission_per_share: commissionPerShare,
      commission_pct: commissionPct,
      benchmark_ticker: benchmarkTicker.trim().toUpperCase() || null,
      seed,
    };

    setRunning(true);
    try {
      const res = await api.backtest.portfolio(req);
      setResult(res);
      toast.success("Portfolio backtest completed");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Portfolio backtest failed");
    } finally {
      setRunning(false);
    }
  }

  // Equity curve data, optionally including benchmark (rebased to initial
  // capital so both lines start at the same y-value).
  const equityCurveData = useMemo(() => {
    if (!result?.equity_curve?.length) return [];
    const benchPairs = result.benchmark_equity_curve ?? [];
    const benchByDate = new Map<string, number>(benchPairs);
    const benchStart = benchPairs.length > 0 ? benchPairs[0][1] : null;
    const initial = result.equity_curve[0]?.[1] ?? initialCapital;
    return result.equity_curve.map(([d, v]) => {
      const benchRaw = benchByDate.get(d);
      const benchScaled =
        benchRaw != null && benchStart != null && benchStart > 0
          ? (benchRaw / benchStart) * initial
          : null;
      return {
        date: new Date(d).toLocaleDateString("en-US", {
          month: "short",
          year: "2-digit",
        }),
        value: v,
        benchmark: benchScaled,
      };
    });
  }, [result, initialCapital]);

  const fillsTotalCount = useMemo(() => {
    if (!result?.fills) return 0;
    return Object.values(result.fills).reduce((acc, arr) => acc + arr.length, 0);
  }, [result]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Strategy"
        title="Portfolio backtest"
        description="Multi-asset replay with scheduled rebalancing, per-ticker P&L, and run-hash reproducibility."
        actions={
          <Button onClick={handleRun} disabled={running} size="sm">
            <Play className="mr-1.5 size-3.5" />
            {running ? "Running…" : "Run portfolio backtest"}
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Configuration */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-4">
            <div className="space-y-1.5">
              <Label>Tickers</Label>
              <Input
                value={tickersRaw}
                onChange={(e) => setTickersRaw(e.target.value)}
                placeholder="AAPL, MSFT, GOOG"
                className="font-mono tabular-nums"
              />
              <p className="text-xs text-muted-foreground">
                Comma- or space-separated. Parsed:{" "}
                <span className="font-mono text-foreground">
                  {tickers.length > 0 ? tickers.join(", ") : "—"}
                </span>
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>
                Weights{" "}
                <span className="text-xs font-normal text-muted-foreground">
                  Optional
                </span>
              </Label>
              <Input
                value={weightsRaw}
                onChange={(e) => setWeightsRaw(e.target.value)}
                placeholder="leave blank for equal-weight"
                className="font-mono tabular-nums"
              />
              <p
                className={cn(
                  "text-xs",
                  weightsValid ? "text-muted-foreground" : "text-loss",
                )}
              >
                {weightHint}
              </p>
            </div>

            <Separator />

            <div className="space-y-1.5">
              <Label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                Rebalance schedule
              </Label>
              <div
                role="radiogroup"
                aria-label="Rebalance schedule"
                className="inline-flex w-full items-center gap-0.5 rounded-md border border-border bg-card p-0.5"
              >
                {REBALANCE_OPTIONS.map((opt) => {
                  const active = opt.value === rebalance;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      role="radio"
                      aria-checked={active}
                      onClick={() => setRebalance(opt.value)}
                      className={cn(
                        "flex-1 rounded-sm px-2 py-1 text-[11px] font-mono uppercase tracking-wider transition-colors duration-150",
                        active
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                      )}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Start date</Label>
                <DatePicker
                  date={startDate}
                  onDateChange={setStartDate}
                  placeholder="Start date"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">End date</Label>
                <DatePicker
                  date={endDate}
                  onDateChange={setEndDate}
                  placeholder="End date"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Initial capital</Label>
              <Input
                type="number"
                value={initialCapital}
                onChange={(e) =>
                  setInitialCapital(parseFloat(e.target.value) || 100000)
                }
                className="font-mono tabular-nums"
              />
            </div>

            <Separator />

            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Slippage (bps)</Label>
                <Input
                  type="number"
                  step="0.5"
                  min="0"
                  value={slippageBps}
                  onChange={(e) =>
                    setSlippageBps(parseFloat(e.target.value) || 0)
                  }
                  className="font-mono tabular-nums"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Comm/share</Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0"
                  value={commissionPerShare}
                  onChange={(e) =>
                    setCommissionPerShare(parseFloat(e.target.value) || 0)
                  }
                  className="font-mono tabular-nums"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Comm %</Label>
                <Input
                  type="number"
                  step="0.0001"
                  min="0"
                  value={commissionPct}
                  onChange={(e) =>
                    setCommissionPct(parseFloat(e.target.value) || 0)
                  }
                  className="font-mono tabular-nums"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">
                  Benchmark{" "}
                  <span className="text-muted-foreground">Optional</span>
                </Label>
                <Input
                  value={benchmarkTicker}
                  onChange={(e) =>
                    setBenchmarkTicker(e.target.value.toUpperCase())
                  }
                  placeholder="SPY"
                  className="font-mono tabular-nums"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Seed</Label>
                <Input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(parseInt(e.target.value) || 0)}
                  className="font-mono tabular-nums"
                />
              </div>
            </div>

            <Button onClick={handleRun} disabled={running} className="w-full">
              <Play className="mr-1.5 size-3.5" />
              {running ? "Running…" : "Run portfolio backtest"}
            </Button>
          </CardContent>
        </Card>

        {/* Results */}
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Results</CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {!result && !running && (
              <div className="space-y-3 py-2">
                <Skeleton className="h-8 w-1/3" />
                <Skeleton className="h-[280px] w-full" />
                <p className="pt-2 text-center text-xs text-muted-foreground">
                  Configure tickers and dates, then run a portfolio backtest.
                </p>
              </div>
            )}

            {running && (
              <div className="space-y-3 py-2">
                <Skeleton className="h-8 w-1/3" />
                <Skeleton className="h-[280px] w-full" />
              </div>
            )}

            {result && !running && (
              <div className="space-y-5">
                {/* Equity curve */}
                <div className="h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={equityCurveData}
                      margin={{ top: 6, right: 6, left: 0, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient
                          id="portfolioGrad"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="var(--primary)"
                            stopOpacity={0.18}
                          />
                          <stop
                            offset="100%"
                            stopColor="var(--primary)"
                            stopOpacity={0}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        strokeDasharray="2 4"
                        stroke="var(--border)"
                        vertical={false}
                      />
                      <XAxis
                        dataKey="date"
                        tick={{
                          fill: "var(--muted-foreground)",
                          fontSize: 11,
                          fontFamily: "var(--font-mono)",
                        }}
                        axisLine={{ stroke: "var(--border)" }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{
                          fill: "var(--muted-foreground)",
                          fontSize: 11,
                          fontFamily: "var(--font-mono)",
                        }}
                        axisLine={{ stroke: "var(--border)" }}
                        tickLine={false}
                        tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                        domain={["auto", "auto"]}
                      />
                      <RechartsTooltip
                        contentStyle={{
                          backgroundColor: "var(--popover)",
                          border: "1px solid var(--border)",
                          borderRadius: "0.375rem",
                          color: "var(--popover-foreground)",
                          fontSize: 12,
                          fontFamily: "var(--font-mono)",
                        }}
                        formatter={(value, name) => [
                          formatCurrency(Number(value)),
                          name === "value" ? "Portfolio" : "Benchmark",
                        ]}
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="var(--primary)"
                        strokeWidth={1.5}
                        dot={false}
                        fill="url(#portfolioGrad)"
                        name="value"
                      />
                      {result.benchmark_equity_curve?.length > 0 && (
                        <Line
                          type="monotone"
                          dataKey="benchmark"
                          stroke="var(--muted-foreground)"
                          strokeWidth={1}
                          strokeDasharray="3 3"
                          dot={false}
                          name="benchmark"
                        />
                      )}
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Summary metrics */}
                <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3 lg:grid-cols-6">
                  <div className="bg-card p-4">
                    <Stat
                      label="Total Return"
                      value={
                        <span
                          className={cn(
                            result.metrics.total_return_pct >= 0
                              ? "text-profit"
                              : "text-loss",
                          )}
                        >
                          {formatPct(result.metrics.total_return_pct)}
                        </span>
                      }
                      trend={result.metrics.total_return_pct}
                    />
                  </div>
                  <div className="bg-card p-4">
                    <Stat
                      label="Sharpe"
                      value={result.metrics.sharpe_ratio.toFixed(2)}
                    />
                  </div>
                  <div className="bg-card p-4">
                    <Stat
                      label="Sortino"
                      value={
                        result.metrics.sortino_ratio?.toFixed(2) ?? "—"
                      }
                    />
                  </div>
                  <div className="bg-card p-4">
                    <Stat
                      label="Calmar"
                      value={result.metrics.calmar_ratio?.toFixed(2) ?? "—"}
                    />
                  </div>
                  <div className="bg-card p-4">
                    <Stat
                      label="Max DD"
                      value={
                        <span className="text-loss">
                          {formatPct(
                            -Math.abs(result.metrics.max_drawdown_pct),
                          )}
                        </span>
                      }
                    />
                  </div>
                  <div className="bg-card p-4">
                    <Stat
                      label="Turnover"
                      value={formatCurrency(result.total_turnover)}
                      sub={`${fillsTotalCount} fills`}
                    />
                  </div>
                </div>

                {/* Per-ticker P&L table */}
                <div className="overflow-hidden rounded-md border border-border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="pl-4">Ticker</TableHead>
                        <TableHead className="text-right">Fills</TableHead>
                        <TableHead className="text-right">Realized</TableHead>
                        <TableHead className="text-right">Unrealized</TableHead>
                        <TableHead className="pr-4 text-right">
                          Final qty
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {tickers.map((t) => {
                        const pnl = result.per_ticker_pnl?.[t] ?? {
                          realized: 0,
                          unrealized: 0,
                        };
                        const fillsCount = result.fills?.[t]?.length ?? 0;
                        const finalQty = result.final_positions?.[t] ?? 0;
                        return (
                          <TableRow key={t}>
                            <TableCell className="pl-4 font-mono font-medium tabular-nums">
                              {t}
                            </TableCell>
                            <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                              {fillsCount}
                            </TableCell>
                            <TableCell
                              className={cn(
                                "text-right font-mono tabular-nums",
                                pnl.realized > 0 && "text-profit",
                                pnl.realized < 0 && "text-loss",
                              )}
                            >
                              {formatCurrency(pnl.realized)}
                            </TableCell>
                            <TableCell
                              className={cn(
                                "text-right font-mono tabular-nums",
                                pnl.unrealized > 0 && "text-profit",
                                pnl.unrealized < 0 && "text-loss",
                              )}
                            >
                              {formatCurrency(pnl.unrealized)}
                            </TableCell>
                            <TableCell className="pr-4 text-right font-mono tabular-nums">
                              {finalQty}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>

                {/* Final cash + run hash */}
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/20 px-4 py-3 text-xs">
                  <span className="text-muted-foreground">
                    Final cash{" "}
                    <span className="font-mono tabular-nums text-foreground">
                      {formatCurrency(result.final_cash)}
                    </span>
                  </span>
                  <span className="text-muted-foreground">
                    run_hash{" "}
                    <span
                      title={result.run_hash}
                      className="font-mono tabular-nums text-foreground"
                    >
                      {result.run_hash.slice(0, 16)}…
                    </span>
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
