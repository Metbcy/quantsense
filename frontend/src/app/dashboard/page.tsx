"use client";

import { useMemo } from "react";
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
import { usePortfolio } from "@/lib/hooks";
import { useFetch } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { ScreenerResult } from "@/lib/api";
import { Loading } from "@/components/loading";

// Generate 30 days of mock portfolio history
function generateMockHistory(currentValue: number) {
  const data = [];
  const now = new Date();
  let val = currentValue * 0.92;
  for (let i = 29; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    val += (Math.random() - 0.45) * currentValue * 0.015;
    val = Math.max(val, currentValue * 0.8);
    data.push({
      date: date.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      value: Math.round(val * 100) / 100,
    });
  }
  // Ensure last point matches current value
  data[data.length - 1].value = currentValue;
  return data;
}

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
  const {
    data: screenerData,
    loading: screenerLoading,
  } = useFetch<ScreenerResult[]>(() => api.market.screener(), []);

  const chartData = useMemo(() => {
    if (!portfolio) return [];
    return generateMockHistory(portfolio.total_value);
  }, [portfolio]);

  if (loading) return <Loading />;

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
        <CardHeader>
          <CardTitle className="text-zinc-100">Portfolio Value</CardTitle>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Holdings Table */}
        <Card className="border-zinc-800 bg-zinc-900 lg:col-span-2">
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
    </div>
  );
}
