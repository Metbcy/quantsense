"use client";

import { useState, useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Activity, BarChart3, Star, Wallet, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Stat } from "@/components/ui/stat";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/page-header";
import { usePortfolio, useFetch, useWatchlist } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { ScreenerResult, TradeRecord } from "@/lib/api";
import { DashboardSkeleton } from "@/components/loading";
import { cn } from "@/lib/utils";

function formatCurrency(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(n);
}

function formatPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function pnlClass(value: number) {
  return value >= 0 ? "text-profit" : "text-loss";
}

const PERIODS = ["1W", "1M", "3M", "1Y", "All"] as const;

export default function DashboardPage() {
  const { portfolio, loading, error } = usePortfolio();
  const { watchlist, loading: watchlistLoading, remove: removeFromWatchlist } = useWatchlist();
  const {
    data: screenerData,
    loading: screenerLoading,
  } = useFetch<ScreenerResult[]>(() => api.market.screener(), []);

  const {
    data: tradesData,
    loading: tradesLoading,
  } = useFetch<{ items: TradeRecord[]; total: number }>(
    () => api.trading.history(1, 10),
    []
  );

  const [period, setPeriod] = useState<string>("1M");
  const {
    data: historyData,
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

  if (loading) return <DashboardSkeleton />;

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 py-20">
        <Activity className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <p className="text-sm text-muted-foreground">Unable to connect to backend</p>
        <p className="font-mono text-xs text-muted-foreground/70">{error}</p>
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 py-20">
        <Wallet className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <p className="text-sm text-muted-foreground">No portfolio data available</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Overview"
        title="Portfolio"
        description="Your paper-trading account at a glance."
      />

      {/* Stat row */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
        <div className="bg-card p-5">
          <Stat label="Total value" value={formatCurrency(portfolio.total_value)} />
        </div>
        <div className="bg-card p-5">
          <Stat
            label="Daily P&L"
            value={formatCurrency(portfolio.daily_pnl)}
            trend={portfolio.daily_pnl}
          />
        </div>
        <div className="bg-card p-5">
          <Stat
            label="Total P&L"
            value={formatCurrency(portfolio.total_pnl)}
            sub={formatPct(portfolio.total_pnl_pct)}
            trend={portfolio.total_pnl}
          />
        </div>
        <div className="bg-card p-5">
          <Stat label="Cash available" value={formatCurrency(portfolio.cash)} />
        </div>
      </div>

      {/* Portfolio Chart */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between border-b">
          <div className="flex flex-col gap-0.5">
            <span className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Equity curve
            </span>
            <CardTitle>Portfolio value</CardTitle>
          </div>
          <div className="flex gap-0.5 rounded-md border border-border p-0.5">
            {PERIODS.map((p) => {
              const key = p.toLowerCase() === "all" ? "all" : p;
              const active = period === key;
              return (
                <button
                  key={p}
                  onClick={() => setPeriod(key)}
                  className={cn(
                    "rounded-sm px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors duration-150",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {p}
                </button>
              );
            })}
          </div>
        </CardHeader>
        <CardContent>
          {chartData.length < 2 ? (
            <div className="flex h-[280px] items-center justify-center">
              <div className="text-center">
                <Activity className="mx-auto mb-2 size-7 text-muted-foreground" strokeWidth={1.5} />
                <p className="text-sm text-foreground">Portfolio history will appear here</p>
                <p className="mt-1 text-xs text-muted-foreground">Snapshots are taken hourly</p>
              </div>
            </div>
          ) : (
            <div className="h-[280px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.22} />
                      <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "var(--muted-foreground)", fontSize: 11, fontFamily: "var(--font-mono)" }}
                    axisLine={{ stroke: "var(--border)" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "var(--muted-foreground)", fontSize: 11, fontFamily: "var(--font-mono)" }}
                    axisLine={{ stroke: "var(--border)" }}
                    tickLine={false}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--popover)",
                      border: "1px solid var(--border)",
                      borderRadius: "0.375rem",
                      color: "var(--popover-foreground)",
                      fontSize: 12,
                      fontFamily: "var(--font-mono)",
                    }}
                    formatter={(value) => [formatCurrency(Number(value)), "Value"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="var(--primary)"
                    strokeWidth={1.5}
                    fill="url(#portfolioGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Holdings Table */}
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Holdings</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            {portfolio.positions.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-4 py-10 text-muted-foreground">
                <Wallet className="mb-2 size-7" strokeWidth={1.5} />
                <p className="text-sm text-foreground">No open positions</p>
                <p className="mt-1 text-xs">Place a trade to get started</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-4">Ticker</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Avg cost</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                    <TableHead className="text-right">P&L</TableHead>
                    <TableHead className="pr-4 text-right">%</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {portfolio.positions.map((pos) => (
                    <TableRow key={pos.ticker}>
                      <TableCell className="pl-4 font-mono font-medium">
                        {pos.ticker}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {pos.quantity}
                      </TableCell>
                      <TableCell className="text-right font-mono text-muted-foreground">
                        {formatCurrency(pos.avg_cost)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatCurrency(pos.current_price)}
                      </TableCell>
                      <TableCell className={cn("text-right font-mono", pnlClass(pos.unrealized_pnl))}>
                        {pos.unrealized_pnl >= 0 ? "+" : ""}
                        {formatCurrency(pos.unrealized_pnl)}
                      </TableCell>
                      <TableCell className={cn("pr-4 text-right font-mono", pnlClass(pos.unrealized_pnl_pct))}>
                        {formatPct(pos.unrealized_pnl_pct)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* Recent Trades */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Recent trades</CardTitle>
          </CardHeader>
          <CardContent>
            {tradesLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : !tradesData?.items?.length ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                <Activity className="mb-2 size-6" strokeWidth={1.5} />
                <p className="text-sm">No trades yet</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {tradesData.items.slice(0, 10).map((trade) => (
                  <div
                    key={trade.id}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <Badge variant={trade.side === "buy" ? "profit" : "loss"}>
                        {trade.side}
                      </Badge>
                      <span className="font-mono text-sm font-medium text-foreground">
                        {trade.ticker}
                      </span>
                      <span className="truncate font-mono text-xs text-muted-foreground">
                        {trade.quantity} @ ${trade.price.toFixed(2)}
                      </span>
                    </div>
                    <span className="font-mono text-[11px] text-muted-foreground">
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
      </div>

      {/* Screener + Watchlist row */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Screener signals</CardTitle>
          </CardHeader>
          <CardContent>
            {screenerLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : !screenerData || screenerData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                <BarChart3 className="mb-2 size-6" strokeWidth={1.5} />
                <p className="text-sm">No signals available</p>
              </div>
            ) : (
              <div className="divide-y divide-border">
                {screenerData.slice(0, 8).map((item) => (
                  <div
                    key={item.ticker}
                    className="flex items-center justify-between gap-3 py-2"
                  >
                    <div className="flex items-baseline gap-3">
                      <span className="font-mono text-sm font-medium text-foreground">
                        {item.ticker}
                      </span>
                      <span className="font-mono text-xs text-muted-foreground">
                        ${item.price.toFixed(2)}
                      </span>
                    </div>
                    <Badge
                      variant={
                        item.signal === "BUY"
                          ? "profit"
                          : item.signal === "SELL"
                            ? "loss"
                            : "secondary"
                      }
                    >
                      {item.signal}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between border-b">
            <CardTitle className="flex items-center gap-1.5">
              <Star className="size-3.5 text-primary" strokeWidth={1.75} />
              Watchlist
            </CardTitle>
          </CardHeader>
          <CardContent>
            {watchlistLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-9" />
                ))}
              </div>
            ) : !watchlist?.length ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                <Star className="mb-2 size-6" strokeWidth={1.5} />
                <p className="text-sm">No watchlist items</p>
                <p className="mt-1 text-xs">Add symbols from the Settings page</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {watchlist.map((item) => (
                  <div
                    key={item.ticker}
                    className="flex items-center justify-between gap-2 rounded-md border border-border px-2.5 py-1.5"
                  >
                    <div className="flex min-w-0 items-baseline gap-2">
                      <span className="font-mono text-sm font-medium text-foreground">
                        {item.ticker}
                      </span>
                      {item.name && (
                        <span className="truncate text-xs text-muted-foreground">
                          {item.name}
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => removeFromWatchlist(item.ticker)}
                      className="text-muted-foreground transition-colors duration-150 hover:text-loss"
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
      </div>
    </div>
  );
}
