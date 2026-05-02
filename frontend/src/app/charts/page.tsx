"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart as RLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { createChart, ColorType, CandlestickSeries, HistogramSeries, LineSeries } from "lightweight-charts";
import type { IChartApi } from "lightweight-charts";
import { Search } from "lucide-react";
import { toast } from "sonner";
import { format as fnsFormat, subMonths, subYears } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/ui/stat";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { OHLCVBar } from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Helpers ────────────────────────────────────────────────────────────────────

function computeSMA(
  data: OHLCVBar[],
  period: number
): { time: string; value: number }[] {
  const result = [];
  for (let i = period - 1; i < data.length; i++) {
    const sum = data
      .slice(i - period + 1, i + 1)
      .reduce((s, d) => s + d.close, 0);
    result.push({ time: data[i].date, value: sum / period });
  }
  return result;
}

function computeRSI(
  data: OHLCVBar[],
  period: number = 14
): { date: string; rsi: number | null }[] {
  const result: { date: string; rsi: number | null }[] = [];
  const gains: number[] = [];
  const losses: number[] = [];

  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      result.push({ date: data[i].date, rsi: null });
      continue;
    }

    const change = data[i].close - data[i - 1].close;
    gains.push(change > 0 ? change : 0);
    losses.push(change < 0 ? -change : 0);

    if (i < period) {
      result.push({ date: data[i].date, rsi: null });
      continue;
    }

    if (i === period) {
      const avgGain = gains.reduce((a, b) => a + b, 0) / period;
      const avgLoss = losses.reduce((a, b) => a + b, 0) / period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push({ date: data[i].date, rsi: 100 - 100 / (1 + rs) });
    } else {
      const prevRsi = result[i - 1].rsi;
      if (prevRsi === null) {
        result.push({ date: data[i].date, rsi: null });
        continue;
      }
      const prevAvgGain =
        (gains.slice(0, -1).reduce((a, b) => a + b, 0) / period) *
          (period - 1) +
        gains[gains.length - 1];
      const prevAvgLoss =
        (losses.slice(0, -1).reduce((a, b) => a + b, 0) / period) *
          (period - 1) +
        losses[losses.length - 1];
      const avgGain = prevAvgGain / period;
      const avgLoss = prevAvgLoss / period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      result.push({ date: data[i].date, rsi: 100 - 100 / (1 + rs) });
    }
  }

  return result;
}

type TimeRange = "1M" | "3M" | "6M" | "1Y" | "2Y" | "5Y" | "10Y" | "ALL";

function getStartDate(range: TimeRange): Date {
  const now = new Date();
  switch (range) {
    case "1M":
      return subMonths(now, 1);
    case "3M":
      return subMonths(now, 3);
    case "6M":
      return subMonths(now, 6);
    case "1Y":
      return subYears(now, 1);
    case "2Y":
      return subYears(now, 2);
    case "5Y":
      return subYears(now, 5);
    case "10Y":
      return subYears(now, 10);
    case "ALL":
      return new Date(2000, 0, 1);
  }
}

function readCssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ChartsPage() {
  const [ticker, setTicker] = useState("");
  const [activeTicker, setActiveTicker] = useState("");
  const [timeRange, setTimeRange] = useState<TimeRange>("6M");
  const [ohlcv, setOhlcv] = useState<OHLCVBar[] | null>(null);
  const [loading, setLoading] = useState(false);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const loadData = useCallback(
    async (sym: string, range: TimeRange) => {
      if (!sym.trim()) return;
      setLoading(true);
      try {
        const end = new Date();
        const start = getStartDate(range);
        const bars = await api.market.ohlcv(
          sym.trim().toUpperCase(),
          fnsFormat(start, "yyyy-MM-dd"),
          fnsFormat(end, "yyyy-MM-dd")
        );
        if (!bars || bars.length === 0) {
          toast.error("No data found for " + sym.toUpperCase());
          setLoading(false);
          return;
        }
        setOhlcv(bars);
        setActiveTicker(sym.trim().toUpperCase());
      } catch (err: unknown) {
        toast.error(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  function handleLoad() {
    if (!ticker.trim()) {
      toast.error("Enter a ticker symbol");
      return;
    }
    loadData(ticker, timeRange);
  }

  function handleTimeRange(range: TimeRange) {
    setTimeRange(range);
    if (activeTicker) {
      loadData(activeTicker, range);
    }
  }

  // Build lightweight chart
  useEffect(() => {
    if (!ohlcv || !chartContainerRef.current) return;

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    const bg = readCssVar("--card", "#fafaf7");
    const text = readCssVar("--muted-foreground", "#71717a");
    const border = readCssVar("--border", "#27272a");
    const profit = readCssVar("--profit", "#22c55e");
    const loss = readCssVar("--loss", "#ef4444");
    const primary = readCssVar("--primary", "#3b82f6");

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: bg },
        textColor: text,
        fontFamily: "var(--font-mono), ui-monospace, monospace",
      },
      grid: {
        vertLines: { color: border, style: 1 },
        horzLines: { color: border, style: 1 },
      },
      width: container.clientWidth,
      height: 420,
      timeScale: { borderColor: border },
      rightPriceScale: { borderColor: border },
      crosshair: {
        horzLine: { color: text },
        vertLine: { color: text },
      },
    });

    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: profit,
      downColor: loss,
      borderDownColor: loss,
      borderUpColor: profit,
      wickDownColor: loss,
      wickUpColor: profit,
    });

    candleSeries.setData(
      ohlcv.map((bar) => ({
        time: bar.date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }))
    );

    // Volume histogram
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    volumeSeries.setData(
      ohlcv.map((bar) => ({
        time: bar.date,
        value: bar.volume,
        color: bar.close >= bar.open ? `${profit}40` : `${loss}40`,
      }))
    );

    // SMA-20 overlay
    const smaData = computeSMA(ohlcv, 20);
    if (smaData.length > 0) {
      const smaSeries = chart.addSeries(LineSeries, {
        color: primary,
        lineWidth: 1,
        priceLineVisible: false,
      });
      smaSeries.setData(smaData);
    }

    chart.timeScale().fitContent();

    // Resize handler
    const handleResize = () => {
      if (chartRef.current && container) {
        chartRef.current.applyOptions({ width: container.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [ohlcv]);

  // Computed values
  const lastBar = ohlcv && ohlcv.length > 0 ? ohlcv[ohlcv.length - 1] : null;
  const firstBar = ohlcv && ohlcv.length > 0 ? ohlcv[0] : null;
  const priceChange =
    lastBar && firstBar ? lastBar.close - firstBar.close : null;
  const priceChangePct =
    lastBar && firstBar && firstBar.close !== 0
      ? ((lastBar.close - firstBar.close) / firstBar.close) * 100
      : null;

  const rsiData = ohlcv ? computeRSI(ohlcv) : [];
  const rsiFiltered = rsiData.filter((d) => d.rsi !== null);

  const timeRanges: TimeRange[] = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "ALL"];

  const high = ohlcv && ohlcv.length ? Math.max(...ohlcv.map((b) => b.high)) : null;
  const low = ohlcv && ohlcv.length ? Math.min(...ohlcv.map((b) => b.low)) : null;
  const avgVol =
    ohlcv && ohlcv.length
      ? Math.round(ohlcv.reduce((s, b) => s + b.volume, 0) / ohlcv.length)
      : null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Market"
        title="Price charts"
        description="Candlestick replays with SMA overlay and RSI indicator."
        actions={
          <div className="flex items-end gap-2">
            <Input
              placeholder="Ticker (e.g. AAPL)"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && handleLoad()}
              className="w-40 font-mono tabular-nums"
            />
            <Button onClick={handleLoad} disabled={loading} size="sm">
              <Search className="mr-1.5 size-3.5" />
              {loading ? "Loading…" : "Load"}
            </Button>
          </div>
        }
      />

      {/* Empty state */}
      {!ohlcv && !loading && (
        <Card>
          <CardContent className="py-10">
            <div className="space-y-3">
              <Skeleton className="h-8 w-1/4" />
              <Skeleton className="h-[280px] w-full" />
              <p className="pt-2 text-center text-xs text-muted-foreground">
                Enter a ticker symbol and click Load to view charts.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="space-y-3">
          <Skeleton className="h-9 w-1/3" />
          <Skeleton className="h-[420px] w-full" />
        </div>
      )}

      {/* Chart area */}
      {ohlcv && !loading && (
        <div className="flex flex-col gap-5">
          {/* Headline + KPI row */}
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-xl font-semibold tabular-nums text-foreground">
                {activeTicker}
              </span>
              {lastBar && (
                <span className="font-mono text-xl tabular-nums text-foreground">
                  ${lastBar.close.toFixed(2)}
                </span>
              )}
              {priceChange !== null && priceChangePct !== null && (
                <span
                  className={cn(
                    "font-mono text-sm tabular-nums",
                    priceChange >= 0 ? "text-profit" : "text-loss",
                  )}
                >
                  {priceChange >= 0 ? "+" : ""}
                  {priceChange.toFixed(2)} ({priceChangePct >= 0 ? "+" : ""}
                  {priceChangePct.toFixed(2)}%)
                </span>
              )}
            </div>
            <div className="flex gap-0.5 rounded-md border border-border p-0.5">
              {timeRanges.map((range) => {
                const active = timeRange === range;
                return (
                  <button
                    key={range}
                    onClick={() => handleTimeRange(range)}
                    className={cn(
                      "rounded-sm px-2 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors duration-150",
                      active
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {range}
                  </button>
                );
              })}
            </div>
          </div>

          {/* KPI strip */}
          {ohlcv.length > 0 && (
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-4">
              <div className="bg-card p-4">
                <Stat
                  label="Last"
                  value={lastBar ? `$${lastBar.close.toFixed(2)}` : "—"}
                  trend={priceChange ?? null}
                  sub={
                    priceChangePct !== null
                      ? `${priceChangePct >= 0 ? "+" : ""}${priceChangePct.toFixed(2)}%`
                      : undefined
                  }
                />
              </div>
              <div className="bg-card p-4">
                <Stat
                  label="Period high"
                  value={high !== null ? `$${high.toFixed(2)}` : "—"}
                />
              </div>
              <div className="bg-card p-4">
                <Stat
                  label="Period low"
                  value={low !== null ? `$${low.toFixed(2)}` : "—"}
                />
              </div>
              <div className="bg-card p-4">
                <Stat
                  label="Avg volume"
                  value={avgVol !== null ? avgVol.toLocaleString() : "—"}
                />
              </div>
            </div>
          )}

          {/* Candlestick chart */}
          <Card>
            <CardContent className="p-2">
              <div ref={chartContainerRef} className="w-full" />
            </CardContent>
          </Card>

          {/* RSI chart */}
          {rsiFiltered.length > 0 && (
            <Card>
              <CardHeader className="border-b">
                <CardTitle>RSI (14)</CardTitle>
              </CardHeader>
              <CardContent className="pt-3">
                <ResponsiveContainer width="100%" height={160}>
                  <RLineChart
                    data={rsiFiltered}
                    margin={{ top: 6, right: 12, left: 0, bottom: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="2 4"
                      stroke="var(--border)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="date"
                      tick={{
                        fill: "var(--muted-foreground)",
                        fontSize: 10,
                        fontFamily: "var(--font-mono)",
                      }}
                      axisLine={{ stroke: "var(--border)" }}
                      tickLine={false}
                      tickFormatter={(v: string) => {
                        const d = new Date(v);
                        return `${d.getMonth() + 1}/${d.getDate()}`;
                      }}
                      minTickGap={40}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{
                        fill: "var(--muted-foreground)",
                        fontSize: 10,
                        fontFamily: "var(--font-mono)",
                      }}
                      axisLine={{ stroke: "var(--border)" }}
                      tickLine={false}
                      ticks={[0, 30, 50, 70, 100]}
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
                      formatter={(value) => [Number(value).toFixed(2), "RSI"]}
                    />
                    <ReferenceLine
                      y={70}
                      stroke="var(--loss)"
                      strokeDasharray="3 3"
                      strokeOpacity={0.5}
                    />
                    <ReferenceLine
                      y={30}
                      stroke="var(--profit)"
                      strokeDasharray="3 3"
                      strokeOpacity={0.5}
                    />
                    <Line
                      type="monotone"
                      dataKey="rsi"
                      stroke="var(--primary)"
                      strokeWidth={1.5}
                      dot={false}
                    />
                  </RLineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
