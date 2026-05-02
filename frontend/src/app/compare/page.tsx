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
import { Play } from "lucide-react";
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
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { CompareResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

function formatPct(n: number) {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
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
      toast.success("Comparison complete");
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
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Analysis"
        title="Strategy comparison"
        description="Run all strategies side-by-side against the same ticker and window."
        actions={
          <Button onClick={handleCompare} disabled={loading} size="sm">
            <Play className="mr-1.5 size-3.5" />
            {loading ? "Running…" : "Compare all"}
          </Button>
        }
      />

      {/* Config */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-1.5">
              <Label className="text-xs">Ticker</Label>
              <Input
                placeholder="AAPL"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                className="font-mono tabular-nums"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Start date</Label>
              <DatePicker
                date={startDate}
                onDateChange={setStartDate}
                placeholder="Start date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">End date</Label>
              <DatePicker
                date={endDate}
                onDateChange={setEndDate}
                placeholder="End date"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Initial capital</Label>
              <Input
                type="number"
                value={capital}
                onChange={(e) => setCapital(e.target.value)}
                className="font-mono tabular-nums"
              />
            </div>
            <Button onClick={handleCompare} disabled={loading}>
              <Play className="mr-1.5 size-3.5" />
              {loading ? "Running…" : "Compare all"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Empty / Loading */}
      {!data && !loading && (
        <Card>
          <CardContent className="py-10">
            <div className="space-y-3">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-32 w-full" />
              <p className="pt-2 text-center text-xs text-muted-foreground">
                Enter a ticker and run comparison to see results.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-9 w-1/4" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {data && !loading && (
        <div className="flex flex-col gap-5">
          {/* Ranked table */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle>
                Rankings ·{" "}
                <span className="font-mono tabular-nums">{data.ticker}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="px-0 pt-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-4">Rank</TableHead>
                    <TableHead>Strategy</TableHead>
                    <TableHead className="text-right">Return</TableHead>
                    <TableHead className="text-right">Sharpe</TableHead>
                    <TableHead className="text-right">Max DD</TableHead>
                    <TableHead className="text-right">Win rate</TableHead>
                    <TableHead className="text-right">Trades</TableHead>
                    <TableHead className="pr-4 text-right">Profit factor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ranked.map((r, i) => {
                    const isWinner = r.winner || i === 0;
                    return (
                      <TableRow
                        key={r.strategy_type}
                        className={cn(isWinner && "bg-primary/5")}
                      >
                        <TableCell className="pl-4 font-mono tabular-nums text-muted-foreground">
                          #{i + 1}
                        </TableCell>
                        <TableCell>
                          <span className="font-medium text-foreground">
                            {r.strategy_name}
                          </span>
                          {isWinner && (
                            <Badge
                              variant="outline"
                              className="ml-2 border-primary/40 font-mono text-[10px] uppercase tracking-wider text-primary"
                            >
                              Winner
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell
                          className={cn(
                            "text-right font-mono tabular-nums",
                            r.metrics.total_return_pct >= 0
                              ? "text-profit"
                              : "text-loss",
                          )}
                        >
                          {formatPct(r.metrics.total_return_pct)}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {r.metrics.sharpe_ratio.toFixed(2)}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-loss">
                          {r.metrics.max_drawdown_pct.toFixed(2)}%
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {(r.metrics.win_rate * 100).toFixed(1)}%
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums">
                          {r.metrics.total_trades}
                        </TableCell>
                        <TableCell className="pr-4 text-right font-mono tabular-nums">
                          {r.metrics.profit_factor.toFixed(2)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Charts row */}
          <div className="grid gap-5 lg:grid-cols-2">
            {/* Return chart */}
            <Card>
              <CardHeader className="border-b">
                <CardTitle>Total return %</CardTitle>
              </CardHeader>
              <CardContent className="pt-3">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={returnChartData}
                    margin={{ top: 6, right: 6, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="2 4"
                      stroke="var(--border)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="name"
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
                      tickFormatter={(v: number) => `${v}%`}
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
                      formatter={(value) => [`${value}%`, "Return"]}
                      cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                    />
                    <Bar dataKey="return" radius={[2, 2, 0, 0]}>
                      {returnChartData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={entry.return >= 0 ? "var(--profit)" : "var(--loss)"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Sharpe chart */}
            <Card>
              <CardHeader className="border-b">
                <CardTitle>Sharpe ratio</CardTitle>
              </CardHeader>
              <CardContent className="pt-3">
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart
                    data={sharpeChartData}
                    margin={{ top: 6, right: 6, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="2 4"
                      stroke="var(--border)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="name"
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
                      formatter={(value) => [Number(value).toFixed(2), "Sharpe"]}
                      cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                    />
                    <Bar dataKey="sharpe" radius={[2, 2, 0, 0]}>
                      {sharpeChartData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={entry.sharpe >= 0 ? "var(--primary)" : "var(--loss)"}
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
