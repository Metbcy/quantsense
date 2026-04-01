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
import { LineChart as LineChartIcon, Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { format as fnsFormat, subMonths, subYears } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { OHLCVBar } from "@/lib/api";

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

type TimeRange = "1M" | "3M" | "6M" | "1Y" | "2Y";

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
  }
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

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0a0f" },
        textColor: "#71717a",
      },
      grid: {
        vertLines: { color: "#1f1f23" },
        horzLines: { color: "#1f1f23" },
      },
      width: container.clientWidth,
      height: 420,
      timeScale: {
        borderColor: "#1f1f23",
      },
      rightPriceScale: {
        borderColor: "#1f1f23",
      },
      crosshair: {
        horzLine: { color: "#3f3f46" },
        vertLine: { color: "#3f3f46" },
      },
    });

    chartRef.current = chart;

    // Candlestick series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
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
        color: bar.close >= bar.open ? "#22c55e40" : "#ef444440",
      }))
    );

    // SMA-20 overlay
    const smaData = computeSMA(ohlcv, 20);
    if (smaData.length > 0) {
      const smaSeries = chart.addSeries(LineSeries, {
        color: "#3b82f6",
        lineWidth: 2,
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

  const timeRanges: TimeRange[] = ["1M", "3M", "6M", "1Y", "2Y"];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-zinc-100">
          <LineChartIcon className="size-6 text-blue-400" />
          Price Charts
        </h1>
        <p className="mt-1 text-sm text-zinc-400">
          Interactive candlestick charts with technical indicators
        </p>
      </div>

      {/* Ticker input */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardContent className="pt-6">
          <div className="flex gap-3 items-end">
            <div className="flex-1 max-w-xs">
              <Input
                placeholder="Enter ticker (e.g. AAPL)"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === "Enter" && handleLoad()}
                className="border-zinc-700 bg-zinc-950 text-zinc-100"
              />
            </div>
            <Button
              onClick={handleLoad}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              {loading ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Search className="mr-2 size-4" />
              )}
              Load
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Empty state */}
      {!ohlcv && !loading && (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <LineChartIcon className="mb-3 size-10" />
          <p>Enter a ticker symbol and click Load to view charts</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="size-8 animate-spin text-blue-400" />
        </div>
      )}

      {/* Chart area */}
      {ohlcv && !loading && (
        <div className="space-y-4">
          {/* Price info + timeframe buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-semibold text-zinc-100">
                {activeTicker}
              </h2>
              {lastBar && (
                <span className="text-lg font-mono text-zinc-200">
                  ${lastBar.close.toFixed(2)}
                </span>
              )}
              {priceChange !== null && priceChangePct !== null && (
                <Badge
                  className={
                    priceChange >= 0
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : "bg-red-500/15 text-red-400 border-red-500/30"
                  }
                >
                  {priceChange >= 0 ? "+" : ""}
                  {priceChange.toFixed(2)} ({priceChangePct >= 0 ? "+" : ""}
                  {priceChangePct.toFixed(2)}%)
                </Badge>
              )}
            </div>
            <div className="flex gap-1">
              {timeRanges.map((range) => (
                <Button
                  key={range}
                  variant={timeRange === range ? "default" : "outline"}
                  size="sm"
                  onClick={() => handleTimeRange(range)}
                  className={
                    timeRange === range
                      ? "bg-blue-600 hover:bg-blue-700 text-white text-xs"
                      : "border-zinc-700 bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 text-xs"
                  }
                >
                  {range}
                </Button>
              ))}
            </div>
          </div>

          {/* Candlestick chart */}
          <Card className="border-zinc-800 bg-zinc-900">
            <CardContent className="p-2">
              <div ref={chartContainerRef} className="w-full" />
            </CardContent>
          </Card>

          {/* RSI chart */}
          {rsiFiltered.length > 0 && (
            <Card className="border-zinc-800 bg-zinc-900">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-zinc-300">
                  RSI (14)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={160}>
                  <RLineChart data={rsiFiltered}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#1f1f23"
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: "#71717a", fontSize: 10 }}
                      axisLine={{ stroke: "#3f3f46" }}
                      tickFormatter={(v: string) => {
                        const d = new Date(v);
                        return `${d.getMonth() + 1}/${d.getDate()}`;
                      }}
                      minTickGap={40}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tick={{ fill: "#71717a", fontSize: 10 }}
                      axisLine={{ stroke: "#3f3f46" }}
                      ticks={[0, 30, 50, 70, 100]}
                    />
                    <RechartsTooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        border: "1px solid #3f3f46",
                        borderRadius: 8,
                        color: "#e4e4e7",
                      }}
                      formatter={(value) => [
                        Number(value).toFixed(2),
                        "RSI",
                      ]}
                    />
                    <ReferenceLine
                      y={70}
                      stroke="#ef4444"
                      strokeDasharray="4 4"
                      strokeOpacity={0.6}
                      label={{
                        value: "Overbought",
                        fill: "#ef4444",
                        fontSize: 10,
                        position: "right",
                      }}
                    />
                    <ReferenceLine
                      y={30}
                      stroke="#22c55e"
                      strokeDasharray="4 4"
                      strokeOpacity={0.6}
                      label={{
                        value: "Oversold",
                        fill: "#22c55e",
                        fontSize: 10,
                        position: "right",
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="rsi"
                      stroke="#a78bfa"
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
