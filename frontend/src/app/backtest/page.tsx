"use client";

import { useState, useEffect, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  Play,
  Loader2,
  Trash2,
  FlaskConical,
  TrendingUp,
  Calendar,
  Info,
  ChevronDown,
  ChevronUp,
  Zap,
  Shield,
  Target,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import { parseISO, format as fnsFormat } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { DatePicker } from "@/components/ui/date-picker";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { useFetch } from "@/lib/hooks";
import { api } from "@/lib/api";
import type {
  StrategyInfo,
  BacktestResult,
  BacktestRequest,
} from "@/lib/api";
import { Loading } from "@/components/loading";

// ── Helpers ──────────────────────────────────────────────────────────────────

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

function defaultDates() {
  const end = new Date();
  const start = new Date();
  start.setFullYear(start.getFullYear() - 1);
  return { start, end };
}

function dateToStr(d: Date | undefined): string {
  if (!d) return "";
  return fnsFormat(d, "yyyy-MM-dd");
}

function strToDate(s: string): Date | undefined {
  if (!s) return undefined;
  try {
    return parseISO(s);
  } catch {
    return undefined;
  }
}

// ── Strategy education content ───────────────────────────────────────────────

const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  momentum:
    "Follows the trend. When a stock\u2019s price rises above its Simple Moving Average (SMA), it signals upward momentum \u2014 time to buy. When it drops below, momentum is fading \u2014 time to sell. The SMA smooths out daily noise by averaging the closing prices over N days (default: 20). Think of it as a \u2018trend confirmation\u2019 tool.",
  mean_reversion:
    "Bets on prices snapping back to normal. The Relative Strength Index (RSI) measures how \u2018overbought\u2019 or \u2018oversold\u2019 a stock is on a 0\u2013100 scale. Below 30 = oversold (buy opportunity), above 70 = overbought (sell signal). It\u2019s based on the idea that extreme price moves tend to reverse.",
  sentiment_momentum:
    "Combines price trends with AI news sentiment. Uses the same SMA crossover as Momentum, but scales position size based on how bullish or bearish the news is. Positive sentiment = bigger positions, negative sentiment = smaller or skip. Best of both worlds \u2014 technical + fundamental.",
  bollinger_bands:
    "Trades the squeeze. Bollinger Bands create an envelope around the price using standard deviations from a moving average. When price touches the lower band, the stock may be undervalued (buy). When it hits the upper band, it may be overvalued (sell). Great for range-bound markets.",
  macd:
    "Tracks momentum shifts. MACD (Moving Average Convergence Divergence) uses two EMAs \u2014 a fast one (12-day) and a slow one (26-day). When the fast crosses above the slow, bullish momentum is building. When it crosses below, momentum is weakening. The histogram shows the gap between them.",
};

const PARAM_TOOLTIPS: Record<string, string> = {
  sma_period:
    "Number of days to average. Higher = smoother but slower to react. Lower = more responsive but more false signals.",
  rsi_period:
    "RSI lookback window. Standard is 14 days. Shorter periods are more sensitive.",
  oversold:
    "RSI level that signals a buying opportunity. Default 30 means the stock has dropped significantly.",
  overbought:
    "RSI level that signals time to sell. Default 70 means the stock has risen significantly.",
  sentiment_weight:
    "How much news sentiment influences position sizing. 0 = ignore sentiment, 1 = sentiment dominates.",
  period:
    "Lookback window for the indicator calculation in days.",
  std_dev:
    "Number of standard deviations for band width. Higher = wider bands, fewer signals.",
  fast:
    "Fast EMA period. Reacts quickly to price changes.",
  slow:
    "Slow EMA period. Captures the longer-term trend.",
  signal:
    "Signal line EMA period. Smooths the MACD line for cleaner crossover signals.",
};

const METRIC_TOOLTIPS: Record<string, string> = {
  "Total Return":
    "Your total profit or loss as a percentage of initial investment",
  "Sharpe Ratio":
    "Risk-adjusted return. Above 1.0 is good, above 2.0 is excellent. Measures return per unit of risk",
  "Max Drawdown":
    "The biggest peak-to-trough decline. Shows the worst loss you would have experienced",
  "Win Rate":
    "Percentage of trades that were profitable",
  "Total Trades":
    "Number of buy+sell round trips executed by the strategy",
  "Profit Factor":
    "Gross profits divided by gross losses. Above 1.0 means profitable, above 2.0 is strong",
  "Avg Trade P&L":
    "Average profit or loss per completed trade",
  "Best Trade":
    "The single most profitable trade",
  "Worst Trade":
    "The single most losing trade",
};

// ── Preset configurations ────────────────────────────────────────────────────

const PRESETS = [
  {
    label: "Conservative",
    icon: Shield,
    strategy: "mean_reversion",
    params: { rsi_period: 14, oversold: 25, overbought: 75 },
  },
  {
    label: "Aggressive",
    icon: Zap,
    strategy: "momentum",
    params: { sma_period: 10 },
  },
  {
    label: "Balanced",
    icon: Target,
    strategy: "sentiment_momentum",
    params: { sma_period: 20, sentiment_weight: 0.3 },
  },
] as const;

// ── Info icon helper ─────────────────────────────────────────────────────────

function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="inline size-3.5 shrink-0 cursor-help text-zinc-500 hover:text-zinc-300" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

// ── Risk score ───────────────────────────────────────────────────────────────

function getRiskLevel(sharpe: number, maxDd: number) {
  const absDd = Math.abs(maxDd);
  if (sharpe > 1.5 && absDd < 10) return { label: "Low Risk", color: "bg-green-500/20 text-green-400" };
  if (sharpe > 0.5 || absDd < 20) return { label: "Medium Risk", color: "bg-yellow-500/20 text-yellow-400" };
  return { label: "High Risk", color: "bg-red-500/20 text-red-400" };
}

// ── Benchmark badge ──────────────────────────────────────────────────────────

function BenchmarkBadge({ result }: { result: BacktestResult }) {
  if (!result.equity_curve || result.equity_curve.length < 2) return null;
  const startVal = result.equity_curve[0][1];
  const endVal = result.equity_curve[result.equity_curve.length - 1][1];
  const buyHoldReturn = ((endVal - startVal) / startVal) * 100;
  const beats = result.metrics.total_return_pct > buyHoldReturn;

  return (
    <Badge
      variant="secondary"
      className={
        beats
          ? "bg-green-500/20 text-green-400"
          : "bg-red-500/20 text-red-400"
      }
    >
      {beats ? "Beats Buy & Hold \u2713" : "Below Buy & Hold \u2717"} vs S&P 500
    </Badge>
  );
}

// ── Main component ───────────────────────────────────────────────────────────

export default function BacktestPage() {
  const { data: strategies, loading: strategiesLoading } = useFetch<StrategyInfo[]>(
    () => api.backtest.strategies(),
    []
  );
  const {
    data: previousResults,
    loading: historyLoading,
    refetch: refetchHistory,
  } = useFetch(() => api.backtest.list().then((r) => r.items), []);

  const dates = useMemo(defaultDates, []);

  const [ticker, setTicker] = useState("AAPL");
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [params, setParams] = useState<Record<string, number>>({});
  const [startDate, setStartDate] = useState<Date | undefined>(dates.start);
  const [endDate, setEndDate] = useState<Date | undefined>(dates.end);
  const [initialCapital, setInitialCapital] = useState(100000);
  const [atrStopMultiplier, setAtrStopMultiplier] = useState<number | undefined>();
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [eduExpanded, setEduExpanded] = useState(false);

  // Set default strategy when strategies load
  useEffect(() => {
    if (strategies && strategies.length > 0 && !selectedStrategy) {
      setSelectedStrategy(strategies[0].name);
      setParams({ ...strategies[0].default_params });
    }
  }, [strategies, selectedStrategy]);

  const currentStrategy = useMemo(
    () => strategies?.find((s) => s.name === selectedStrategy),
    [strategies, selectedStrategy]
  );

  function handleStrategyChange(value: string | null) {
    if (!value) return;
    setSelectedStrategy(value);
    setEduExpanded(false);
    const strat = strategies?.find((s) => s.name === value);
    if (strat) setParams({ ...strat.default_params });
  }

  function applyPreset(preset: (typeof PRESETS)[number]) {
    setSelectedStrategy(preset.strategy);
    setParams({ ...preset.params });
    setEduExpanded(false);
    const strat = strategies?.find((s) => s.name === preset.strategy);
    if (strat) {
      setParams({ ...strat.default_params, ...preset.params });
    }
  }

  async function handleRun() {
    if (!ticker.trim() || !selectedStrategy) {
      toast.error("Please fill in ticker and strategy");
      return;
    }

    setRunning(true);
    try {
      const req: BacktestRequest = {
        ticker: ticker.toUpperCase(),
        strategy_type: selectedStrategy,
        start_date: dateToStr(startDate),
        end_date: dateToStr(endDate),
        initial_capital: initialCapital,
        params,
        atr_stop_multiplier: atrStopMultiplier,
      };
      const res = await api.backtest.run(req);
      setResult(res);
      refetchHistory();
      toast.success("Backtest completed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.backtest.delete(id);
      refetchHistory();
      toast.success("Result deleted");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const equityCurveData = useMemo(() => {
    if (!result?.equity_curve) return [];
    return result.equity_curve.map(([date, value]) => ({
      date: new Date(date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      }),
      value,
    }));
  }, [result]);

  const riskLevel = useMemo(() => {
    if (!result) return null;
    return getRiskLevel(result.metrics.sharpe_ratio, result.metrics.max_drawdown_pct);
  }, [result]);

  const eduDescription = STRATEGY_DESCRIPTIONS[selectedStrategy] ?? null;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-6 p-6">
        <div className="flex items-center gap-3">
          <FlaskConical className="size-6 text-blue-500" />
          <h1 className="text-2xl font-bold text-zinc-100">Backtesting</h1>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Configuration Panel */}
          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader>
              <CardTitle className="text-zinc-100">Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Quick Presets */}
              <div className="space-y-2">
                <Label className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                  Quick Presets
                </Label>
                <div className="grid grid-cols-3 gap-2">
                  {PRESETS.map((p) => (
                    <Button
                      key={p.label}
                      variant="outline"
                      size="sm"
                      onClick={() => applyPreset(p)}
                      className="border-zinc-700 bg-zinc-950 text-zinc-300 hover:bg-zinc-800 hover:text-zinc-100"
                    >
                      <p.icon className="mr-1 size-3.5" />
                      {p.label}
                    </Button>
                  ))}
                </div>
              </div>

              <Separator className="bg-zinc-800" />

              <div className="space-y-2">
                <Label className="text-zinc-400">Ticker</Label>
                <Input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="e.g. AAPL"
                  className="border-zinc-700 bg-zinc-950 font-mono text-zinc-100 placeholder:text-zinc-600"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-zinc-400">Strategy</Label>
                {strategiesLoading ? (
                  <div className="h-8 animate-pulse rounded bg-zinc-800" />
                ) : (
                  <Select
                    value={selectedStrategy}
                    onValueChange={handleStrategyChange}
                  >
                    <SelectTrigger className="w-full border-zinc-700 bg-zinc-950 text-zinc-100">
                      <SelectValue placeholder="Select strategy" />
                    </SelectTrigger>
                    <SelectContent className="border-zinc-700 bg-zinc-900">
                      {strategies?.map((s) => (
                        <SelectItem key={s.name} value={s.name}>
                          {s.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {currentStrategy && (
                  <p className="text-xs text-zinc-500">
                    {currentStrategy.description}
                  </p>
                )}
              </div>

              {/* Strategy Education Card */}
              {eduDescription && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                  <button
                    type="button"
                    onClick={() => setEduExpanded(!eduExpanded)}
                    className="flex w-full items-center justify-between text-left"
                  >
                    <span className="flex items-center gap-2 text-xs font-medium text-blue-400">
                      <Info className="size-3.5" />
                      How does this strategy work?
                    </span>
                    {eduExpanded ? (
                      <ChevronUp className="size-3.5 text-zinc-500" />
                    ) : (
                      <ChevronDown className="size-3.5 text-zinc-500" />
                    )}
                  </button>
                  {eduExpanded && (
                    <p className="mt-2 text-xs leading-relaxed text-zinc-400">
                      {eduDescription}
                    </p>
                  )}
                </div>
              )}

              {/* Dynamic Strategy Params */}
              {currentStrategy &&
                Object.keys(currentStrategy.default_params).length > 0 && (
                  <>
                    <Separator className="bg-zinc-800" />
                    <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                      Parameters
                    </p>
                    {Object.entries(currentStrategy.default_params).map(
                      ([key, defaultVal]) => (
                        <div key={key} className="space-y-1">
                          <Label className="flex items-center gap-1.5 text-xs text-zinc-500">
                            {key.replace(/_/g, " ")}
                            {PARAM_TOOLTIPS[key] && (
                              <InfoTip text={PARAM_TOOLTIPS[key]} />
                            )}
                          </Label>
                          <Input
                            type="number"
                            value={params[key] ?? defaultVal}
                            onChange={(e) =>
                              setParams((p) => ({
                                ...p,
                                [key]: parseFloat(e.target.value) || 0,
                              }))
                            }
                            className="border-zinc-700 bg-zinc-950 text-zinc-100"
                          />
                        </div>
                      )
                    )}
                  </>
                )}

              <Separator className="bg-zinc-800" />

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-500">Start Date</Label>
                  <DatePicker
                    date={startDate}
                    onDateChange={setStartDate}
                    placeholder="Start date"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs text-zinc-500">End Date</Label>
                  <DatePicker
                    date={endDate}
                    onDateChange={setEndDate}
                    placeholder="End date"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-zinc-400">Initial Capital</Label>
                <Input
                  type="number"
                  value={initialCapital}
                  onChange={(e) =>
                    setInitialCapital(parseFloat(e.target.value) || 100000)
                  }
                  className="border-zinc-700 bg-zinc-950 text-zinc-100"
                />
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label className="text-zinc-400">ATR Stop Multiplier</Label>
                  <span className="text-xs text-zinc-500">(Optional)</span>
                </div>
                <Input
                  type="number"
                  step="0.1"
                  min="0"
                  value={atrStopMultiplier === undefined ? "" : atrStopMultiplier}
                  onChange={(e) => {
                    const val = e.target.value;
                    setAtrStopMultiplier(val === "" ? undefined : parseFloat(val));
                  }}
                  placeholder="e.g. 2.0"
                  className="border-zinc-700 bg-zinc-950 text-zinc-100 placeholder:text-zinc-600"
                />
                <p className="text-xs text-zinc-500 mt-1">
                  Dynamic trailing stop based on Average True Range volatility.
                </p>
              </div>

              <Button
                onClick={handleRun}
                disabled={running}
                className="w-full bg-blue-600 text-white hover:bg-blue-700"
              >
                {running ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <Play className="mr-2 size-4" />
                )}
                {running ? "Running\u2026" : "Run Backtest"}
              </Button>
            </CardContent>
          </Card>

          {/* Results Panel */}
          <Card className="border-zinc-800 bg-zinc-900 lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-zinc-100">Results</CardTitle>
              {result && (
                <a
                  href={api.backtest.exportCsv(result.id)}
                  download
                  className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 transition-colors"
                >
                  <Download className="size-3.5" />
                  Export CSV
                </a>
              )}
            </CardHeader>
            <CardContent>
              {!result ? (
                <div className="flex flex-col items-center justify-center py-16 text-zinc-500">
                  <TrendingUp className="mb-3 size-10" />
                  <p>Configure and run a backtest to see results</p>
                </div>
              ) : (
                <Tabs defaultValue="equity">
                  <TabsList className="border-zinc-700 bg-zinc-800">
                    <TabsTrigger value="equity">Equity Curve</TabsTrigger>
                    <TabsTrigger value="trades">Trades</TabsTrigger>
                    <TabsTrigger value="metrics">Metrics</TabsTrigger>
                  </TabsList>

                  <TabsContent value="equity" className="mt-4">
                    <div className="h-[350px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={equityCurveData}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                          <XAxis
                            dataKey="date"
                            tick={{ fill: "#71717a", fontSize: 11 }}
                            axisLine={{ stroke: "#3f3f46" }}
                            tickLine={false}
                          />
                          <YAxis
                            tick={{ fill: "#71717a", fontSize: 11 }}
                            axisLine={{ stroke: "#3f3f46" }}
                            tickLine={false}
                            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                            domain={["auto", "auto"]}
                          />
                          <RechartsTooltip
                            contentStyle={{
                              backgroundColor: "#18181b",
                              border: "1px solid #3f3f46",
                              borderRadius: "8px",
                              color: "#f4f4f5",
                            }}
                            formatter={(value) => [
                              formatCurrency(Number(value)),
                              "Portfolio",
                            ]}
                          />
                          <Line
                            type="monotone"
                            dataKey="value"
                            stroke="#3b82f6"
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </TabsContent>

                  <TabsContent value="trades" className="mt-4">
                    {result.trades.length === 0 ? (
                      <p className="py-8 text-center text-zinc-500">No trades</p>
                    ) : (
                      <div className="max-h-[400px] overflow-y-auto">
                        <Table>
                          <TableHeader>
                            <TableRow className="border-zinc-800 hover:bg-transparent">
                              <TableHead className="text-zinc-400">Date</TableHead>
                              <TableHead className="text-zinc-400">Side</TableHead>
                              <TableHead className="text-right text-zinc-400">
                                Price
                              </TableHead>
                              <TableHead className="text-right text-zinc-400">
                                Qty
                              </TableHead>
                              <TableHead className="text-right text-zinc-400">
                                Value
                              </TableHead>
                              <TableHead className="text-right text-zinc-400">
                                P&L
                              </TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {result.trades.map((trade, i) => {
                              const isBuy = trade.side.toUpperCase() === "BUY";
                              return (
                                <TableRow key={i} className="border-zinc-800">
                                  <TableCell className="text-zinc-300">
                                    {new Date(trade.date).toLocaleDateString()}
                                  </TableCell>
                                  <TableCell>
                                    <Badge
                                      variant="secondary"
                                      className={
                                        isBuy
                                          ? "bg-green-500/20 text-green-400"
                                          : "bg-red-500/20 text-red-400"
                                      }
                                    >
                                      {trade.side.toUpperCase()}
                                    </Badge>
                                  </TableCell>
                                  <TableCell className="text-right font-mono text-zinc-300">
                                    {formatCurrency(trade.price)}
                                  </TableCell>
                                  <TableCell className="text-right text-zinc-300">
                                    {trade.quantity}
                                  </TableCell>
                                  <TableCell className="text-right text-zinc-300">
                                    {formatCurrency(trade.value)}
                                  </TableCell>
                                  <TableCell
                                    className={`text-right font-mono ${
                                      trade.pnl >= 0 ? "text-green-500" : "text-red-500"
                                    }`}
                                  >
                                    {trade.pnl !== 0
                                      ? `${trade.pnl >= 0 ? "+" : ""}${formatCurrency(trade.pnl)}`
                                      : "\u2014"}
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="metrics" className="mt-4 space-y-4">
                    {/* Benchmark + Risk badges */}
                    <div className="flex flex-wrap items-center gap-2">
                      <BenchmarkBadge result={result} />
                      {riskLevel && (
                        <Badge variant="secondary" className={riskLevel.color}>
                          {riskLevel.label}
                        </Badge>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                      {[
                        {
                          label: "Total Return",
                          value: formatPct(result.metrics.total_return_pct),
                          color:
                            result.metrics.total_return_pct >= 0
                              ? "text-green-500"
                              : "text-red-500",
                        },
                        {
                          label: "Sharpe Ratio",
                          value: result.metrics.sharpe_ratio.toFixed(2),
                          color: "text-blue-400",
                        },
                        {
                          label: "Max Drawdown",
                          value: formatPct(-Math.abs(result.metrics.max_drawdown_pct)),
                          color: "text-red-400",
                        },
                        {
                          label: "Win Rate",
                          value: `${(result.metrics.win_rate * 100).toFixed(1)}%`,
                          color: "text-zinc-100",
                        },
                        {
                          label: "Total Trades",
                          value: result.metrics.total_trades.toString(),
                          color: "text-zinc-100",
                        },
                        {
                          label: "Profit Factor",
                          value: result.metrics.profit_factor.toFixed(2),
                          color:
                            result.metrics.profit_factor >= 1
                              ? "text-green-500"
                              : "text-red-500",
                        },
                        {
                          label: "Avg Trade P&L",
                          value: formatCurrency(result.metrics.avg_trade_pnl),
                          color:
                            result.metrics.avg_trade_pnl >= 0
                              ? "text-green-500"
                              : "text-red-500",
                        },
                        {
                          label: "Best Trade",
                          value: formatCurrency(result.metrics.best_trade_pnl),
                          color: "text-green-500",
                        },
                        {
                          label: "Worst Trade",
                          value: formatCurrency(result.metrics.worst_trade_pnl),
                          color: "text-red-500",
                        },
                      ].map((m) => (
                        <div
                          key={m.label}
                          className="rounded-lg border border-zinc-800 bg-zinc-950 p-3"
                        >
                          <p className="flex items-center gap-1.5 text-xs text-zinc-500">
                            {m.label}
                            {METRIC_TOOLTIPS[m.label] && (
                              <InfoTip text={METRIC_TOOLTIPS[m.label]} />
                            )}
                          </p>
                          <p className={`mt-1 text-lg font-semibold ${m.color}`}>
                            {m.value}
                          </p>
                        </div>
                      ))}
                    </div>
                  </TabsContent>
                </Tabs>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Previous Results */}
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-zinc-100">
              <Calendar className="size-4" />
              Previous Runs
            </CardTitle>
          </CardHeader>
          <CardContent>
            {historyLoading ? (
              <Loading />
            ) : !previousResults || previousResults.length === 0 ? (
              <p className="py-6 text-center text-sm text-zinc-500">
                No previous backtests
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="border-zinc-800 hover:bg-transparent">
                    <TableHead className="text-zinc-400">Ticker</TableHead>
                    <TableHead className="text-zinc-400">Strategy</TableHead>
                    <TableHead className="text-right text-zinc-400">Return</TableHead>
                    <TableHead className="text-right text-zinc-400">Sharpe</TableHead>
                    <TableHead className="text-right text-zinc-400">
                      Max DD
                    </TableHead>
                    <TableHead className="text-right text-zinc-400">Trades</TableHead>
                    <TableHead className="text-zinc-400">Date</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {previousResults.map((r) => (
                    <TableRow
                      key={r.id}
                      className="cursor-pointer border-zinc-800 hover:bg-zinc-800/50"
                      onClick={() => setResult(r)}
                    >
                      <TableCell className="font-mono font-semibold text-zinc-100">
                        {r.ticker}
                      </TableCell>
                      <TableCell className="text-zinc-400">
                        {r.strategy_type}
                      </TableCell>
                      <TableCell
                        className={`text-right font-mono ${
                          r.metrics.total_return_pct >= 0
                            ? "text-green-500"
                            : "text-red-500"
                        }`}
                      >
                        {formatPct(r.metrics.total_return_pct)}
                      </TableCell>
                      <TableCell className="text-right text-zinc-300">
                        {r.metrics.sharpe_ratio.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right text-red-400">
                        {formatPct(-Math.abs(r.metrics.max_drawdown_pct))}
                      </TableCell>
                      <TableCell className="text-right text-zinc-300">
                        {r.metrics.total_trades}
                      </TableCell>
                      <TableCell className="text-xs text-zinc-500">
                        {new Date(r.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(r.id);
                          }}
                          className="text-zinc-500 hover:text-red-400"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </TooltipProvider>
  );
}
