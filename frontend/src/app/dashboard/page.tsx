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
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Wallet,
  BarChart3,
  Activity,
  Star,
  X,
} from "lucide-react";
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
import { usePortfolio, useFetch, useWatchlist } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { ScreenerResult, TradeRecord } from "@/lib/api";
import { DashboardSkeleton } from "@/components/loading";

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

function PnlText({ value, className = "" }: { value: number; className?: string }) {
  return (
    <span className={`${value >= 0 ? "text-green-500" : "text-red-500"} ${className}`}>
      {value >= 0 ? "+" : ""}
      {formatCurrency(value)}
    </span>
  );
}

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

  if (loading) return <DashboardSkeleton />;

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 py-20">
        <Activity className="size-12 text-zinc-600" />
        <p className="text-zinc-400">Unable to connect to backend</p>
        <p className="text-sm text-zinc-600">{error}</p>
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 py-20">
        <Wallet className="size-12 text-zinc-600" />
        <p className="text-zinc-400">No portfolio data available</p>
      </div>
    );
  }

  const stats = [
    {
      title: "Total Value",
      value: formatCurrency(portfolio.total_value),
      icon: DollarSign,
      change: null,
    },
    {
      title: "Daily P&L",
      value: formatCurrency(portfolio.daily_pnl),
      icon: portfolio.daily_pnl >= 0 ? TrendingUp : TrendingDown,
      change: portfolio.daily_pnl,
      color: portfolio.daily_pnl >= 0 ? "text-green-500" : "text-red-500",
    },
    {
      title: "Total P&L",
      value: formatCurrency(portfolio.total_pnl),
      icon: BarChart3,
      change: portfolio.total_pnl,
      pct: portfolio.total_pnl_pct,
      color: portfolio.total_pnl >= 0 ? "text-green-500" : "text-red-500",
    },
    {
      title: "Cash Available",
      value: formatCurrency(portfolio.cash),
      icon: Wallet,
      change: null,
    },
  ];

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card
            key={stat.title}
            className="border-zinc-800 bg-zinc-900"
          >
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-zinc-400">
                {stat.title}
              </CardTitle>
              <stat.icon className={`size-4 ${stat.color || "text-zinc-500"}`} />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${stat.color || "text-zinc-100"}`}>
                {stat.value}
              </div>
              {stat.pct !== undefined && (
                <p className={`mt-1 text-xs ${stat.color}`}>
                  {formatPct(stat.pct)}
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Portfolio Chart */}
      <Card className="border-zinc-800 bg-zinc-900">
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
        <CardContent>
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
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#71717a", fontSize: 12 }}
                    axisLine={{ stroke: "#3f3f46" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: "#71717a", fontSize: 12 }}
                    axisLine={{ stroke: "#3f3f46" }}
                    tickLine={false}
                    tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                    domain={["auto", "auto"]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#18181b",
                      border: "1px solid #3f3f46",
                      borderRadius: "8px",
                      color: "#f4f4f5",
                    }}
                    formatter={(value) => [formatCurrency(Number(value)), "Value"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fill="url(#portfolioGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Holdings Table */}
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader>
            <CardTitle className="text-zinc-100">Holdings</CardTitle>
          </CardHeader>
          <CardContent>
            {portfolio.positions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-zinc-500">
                <Wallet className="mb-3 size-8" />
                <p>No open positions</p>
                <p className="mt-1 text-xs text-zinc-600">
                  Place a trade to get started
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-zinc-400">Ticker</TableHead>
                    <TableHead className="text-right text-zinc-400">Qty</TableHead>
                    <TableHead className="text-right text-zinc-400">Avg Cost</TableHead>
                    <TableHead className="text-right text-zinc-400">Price</TableHead>
                    <TableHead className="text-right text-zinc-400">P&L</TableHead>
                    <TableHead className="text-right text-zinc-400">%</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {portfolio.positions.map((pos) => (
                    <TableRow key={pos.ticker} className="border-zinc-800">
                      <TableCell className="font-mono font-semibold text-zinc-100">
                        {pos.ticker}
                      </TableCell>
                      <TableCell className="text-right text-zinc-300">
                        {pos.quantity}
                      </TableCell>
                      <TableCell className="text-right text-zinc-300">
                        {formatCurrency(pos.avg_cost)}
                      </TableCell>
                      <TableCell className="text-right text-zinc-300">
                        {formatCurrency(pos.current_price)}
                      </TableCell>
                      <TableCell className="text-right">
                        <PnlText value={pos.unrealized_pnl} />
                      </TableCell>
                      <TableCell className="text-right">
                        <span
                          className={
                            pos.unrealized_pnl_pct >= 0
                              ? "text-green-500"
                              : "text-red-500"
                          }
                        >
                          {formatPct(pos.unrealized_pnl_pct)}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

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

        {/* Screener */}
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader>
            <CardTitle className="text-zinc-100">Screener Signals</CardTitle>
          </CardHeader>
          <CardContent>
            {screenerLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 animate-pulse rounded bg-zinc-800" />
                ))}
              </div>
            ) : !screenerData || screenerData.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-zinc-500">
                <BarChart3 className="mb-2 size-6" />
                <p className="text-sm">No signals available</p>
              </div>
            ) : (
              <div className="space-y-3">
                {screenerData.slice(0, 8).map((item) => (
                  <div
                    key={item.ticker}
                    className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
                  >
                    <div>
                      <span className="font-mono font-semibold text-zinc-100">
                        {item.ticker}
                      </span>
                      <span className="ml-2 text-xs text-zinc-500">
                        ${item.price.toFixed(2)}
                      </span>
                    </div>
                    <Badge
                      variant={
                        item.signal === "BUY"
                          ? "default"
                          : item.signal === "SELL"
                            ? "destructive"
                            : "secondary"
                      }
                      className={
                        item.signal === "BUY"
                          ? "bg-green-500/20 text-green-400"
                          : item.signal === "SELL"
                            ? "bg-red-500/20 text-red-400"
                            : ""
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
      </div>

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
    </div>
  );
}
