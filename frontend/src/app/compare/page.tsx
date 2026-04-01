"use client";

import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import { BarChart3, Loader2, Play } from "lucide-react";
import { toast } from "sonner";
import { format as fnsFormat } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { DatePicker } from "@/components/ui/date-picker";
import { api } from "@/lib/api";
import type { CompareResponse, CompareResult } from "@/lib/api";

function formatPct(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function formatCurrency(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
  }).format(n);
}

export default function ComparePage() {
  const [ticker, setTicker] = useState("");
  const [startDate, setStartDate] = useState<Date | undefined>(undefined);
  const [endDate, setEndDate] = useState<Date | undefined>(undefined);
  const [capital, setCapital] = useState("100000");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CompareResponse | null>(null);

  async function handleCompare() {
    if (!ticker.trim()) {
      toast.error("Enter a ticker symbol");
      return;
    }
    if (!startDate || !endDate) {
      toast.error("Select start and end dates");
      return;
    }

    setLoading(true);
    try {
      const result = await api.backtest.compare(
        ticker.trim().toUpperCase(),
        fnsFormat(startDate, "yyyy-MM-dd"),
        fnsFormat(endDate, "yyyy-MM-dd"),
        Number(capital) || 100000
      );
      setData(result);
      toast.success("Comparison complete!");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Comparison failed");
    } finally {
      setLoading(false);
    }
  }

  const ranked = data
    ? [...data.results].sort(
        (a, b) => b.metrics.total_return_pct - a.metrics.total_return_pct
      )
    : [];

  const returnChartData = ranked.map((r) => ({
    name: r.strategy_name,
    return: Number(r.metrics.total_return_pct.toFixed(2)),
  }));

  const sharpeChartData = ranked.map((r) => ({
    name: r.strategy_name,
    sharpe: Number(r.metrics.sharpe_ratio.toFixed(2)),
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-zinc-100">
          <BarChart3 className="size-6 text-blue-400" />
          Strategy Comparison
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Run all 5 strategies against the same ticker to find the best one
        </p>
      </div>

      {/* Config */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardContent className="pt-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5 items-end">
            <div className="space-y-1.5">
              <Label className="text-zinc-400">Ticker</Label>
              <Input
                placeholder="AAPL"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                className="border-zinc-700 bg-zinc-950 text-zinc-100"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-zinc-400">Start Date</Label>
              <DatePicker
                date={startDate}
                onDateChange={setStartDate}
                placeholder="Start date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-zinc-400">End Date</Label>
              <DatePicker
                date={endDate}
                onDateChange={setEndDate}
                placeholder="End date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-zinc-400">Initial Capital</Label>
              <Input
                type="number"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                className="border-zinc-700 bg-zinc-950 text-zinc-100"
              />
            </div>
            <Button
              onClick={handleCompare}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              {loading ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Play className="mr-2 size-4" />
              )}
              {loading ? "Running…" : "Compare All"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {!data && !loading && (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <BarChart3 className="mb-3 size-10" />
          <p>Enter a ticker and run comparison to see results</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="size-8 animate-spin text-blue-400" />
        </div>
      )}

      {data && !loading && (
        <div className="space-y-6">
          {/* Ranked table */}
          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader>
              <CardTitle className="text-zinc-100">
                Rankings — {data.ticker}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="border-zinc-800">
                      <TableHead className="text-zinc-400">Rank</TableHead>
                      <TableHead className="text-zinc-400">Strategy</TableHead>
                      <TableHead className="text-zinc-400 text-right">Return</TableHead>
                      <TableHead className="text-zinc-400 text-right">Sharpe</TableHead>
                      <TableHead className="text-zinc-400 text-right">Max DD</TableHead>
                      <TableHead className="text-zinc-400 text-right">Win Rate</TableHead>
                      <TableHead className="text-zinc-400 text-right">Trades</TableHead>
                      <TableHead className="text-zinc-400 text-right">Profit Factor</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ranked.map((r, i) => {
                      const isWinner = r.winner || i === 0;
                      return (
                        <TableRow
                          key={r.strategy_type}
                          className={
                            isWinner
                              ? "border-yellow-500/40 bg-yellow-500/5"
                              : "border-zinc-800"
                          }
                        >
                          <TableCell className="font-medium text-zinc-300">
                            {isWinner ? "👑" : `#${i + 1}`}
                          </TableCell>
                          <TableCell>
                            <span className="font-medium text-zinc-100">
                              {r.strategy_name}
                            </span>
                            {isWinner && (
                              <Badge className="ml-2 bg-yellow-500/20 text-yellow-400 border-yellow-500/30 text-[10px]">
                                Winner
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell
                            className={`text-right font-mono ${
                              r.metrics.total_return_pct >= 0
                                ? "text-emerald-400"
                                : "text-red-400"
                            }`}
                          >
                            {formatPct(r.metrics.total_return_pct)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-zinc-300">
                            {r.metrics.sharpe_ratio.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-red-400">
                            {r.metrics.max_drawdown_pct.toFixed(2)}%
                          </TableCell>
                          <TableCell className="text-right font-mono text-zinc-300">
                            {(r.metrics.win_rate * 100).toFixed(1)}%
                          </TableCell>
                          <TableCell className="text-right font-mono text-zinc-300">
                            {r.metrics.total_trades}
                          </TableCell>
                          <TableCell className="text-right font-mono text-zinc-300">
                            {r.metrics.profit_factor.toFixed(2)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Charts row */}
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Return chart */}
            <Card className="border-zinc-800 bg-zinc-900">
              <CardHeader>
                <CardTitle className="text-sm text-zinc-300">
                  Total Return %
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={returnChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={{ stroke: "#3f3f46" }}
                    />
                    <YAxis
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={{ stroke: "#3f3f46" }}
                      tickFormatter={(v: number) => `${v}%`}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #3f3f46",
                        borderRadius: 8,
                        color: "#e4e4e7",
                      }}
                      formatter={(value) => [`${value}%`, "Return"]}
                    />
                    <Bar dataKey="return" radius={[4, 4, 0, 0]}>
                      {returnChartData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={entry.return >= 0 ? "#34d399" : "#f87171"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Sharpe chart */}
            <Card className="border-zinc-800 bg-zinc-900">
              <CardHeader>
                <CardTitle className="text-sm text-zinc-300">
                  Sharpe Ratio
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={sharpeChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={{ stroke: "#3f3f46" }}
                    />
                    <YAxis
                      tick={{ fill: "#71717a", fontSize: 11 }}
                      axisLine={{ stroke: "#3f3f46" }}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #3f3f46",
                        borderRadius: 8,
                        color: "#e4e4e7",
                      }}
                      formatter={(value) => [Number(value).toFixed(2), "Sharpe"]}
                    />
                    <Bar dataKey="sharpe" radius={[4, 4, 0, 0]}>
                      {sharpeChartData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={entry.sharpe >= 0 ? "#60a5fa" : "#f87171"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
