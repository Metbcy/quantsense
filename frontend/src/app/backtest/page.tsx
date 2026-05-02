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
  Trash2,
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
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/ui/stat";
import { Skeleton } from "@/components/ui/skeleton";
import { useFetch } from "@/lib/hooks";
import { api } from "@/lib/api";
import type {
  StrategyInfo,
  BacktestResult,
  BacktestRequest,
  SignificanceResponse,
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

// strToDate kept for potential future use
function _strToDate(s: string): Date | undefined {
  if (!s) return undefined;
  try {
    return parseISO(s);
  } catch {
    return undefined;
  }
}
void _strToDate;

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
  "Sortino Ratio":
    "Downside-risk-adjusted return. Like Sharpe, but only penalizes downside volatility.",
  "Calmar Ratio":
    "Annualized return divided by max drawdown. Higher = better return per unit of drawdown.",
  "Deflated Sharpe":
    "Sharpe ratio adjusted for the number of trials and non-normality. Closer to truth.",
  "DD Duration":
    "Longest stretch of bars spent under a previous equity peak.",
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
        <Info className="inline size-3.5 shrink-0 cursor-help text-muted-foreground hover:text-foreground" />
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
  if (sharpe > 1.5 && absDd < 10)
    return { label: "Low risk", tone: "profit" as const };
  if (sharpe > 0.5 || absDd < 20)
    return { label: "Medium risk", tone: "neutral" as const };
  return { label: "High risk", tone: "loss" as const };
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
      variant="outline"
      className={cn(
        "border-border font-mono text-[10.5px] uppercase tracking-wider",
        beats ? "text-profit" : "text-loss",
      )}
    >
      {beats ? "Beats" : "Below"} buy &amp; hold · S&amp;P 500
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
  const [significance, setSignificance] = useState<SignificanceResponse | null>(null);
  const [sigRunning, setSigRunning] = useState(false);
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
      setSignificance(null);
      refetchHistory();
      toast.success("Backtest completed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  }

  async function handleSignificance() {
    if (!ticker.trim() || !selectedStrategy) return;
    setSigRunning(true);
    try {
      const res = await api.backtest.significance({
        ticker: ticker.toUpperCase(),
        strategy_type: selectedStrategy,
        start_date: dateToStr(startDate),
        end_date: dateToStr(endDate),
        initial_capital: initialCapital,
        params,
      });
      setSignificance(res);
      toast.success("Significance test complete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Significance test failed");
    } finally {
      setSigRunning(false);
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

  // ── KPI configuration ──────────────────────────────────────────────────────

  type StatTone = "profit" | "loss" | "neutral";
  type StatRow = {
    label: string;
    value: string;
    sub?: string;
    trend?: number | null;
    tone?: StatTone;
  };

  const statRows: StatRow[] = result
    ? [
        {
          label: "Total Return",
          value: formatPct(result.metrics.total_return_pct),
          trend: result.metrics.total_return_pct,
        },
        {
          label: "Sharpe Ratio",
          value: result.metrics.sharpe_ratio.toFixed(2),
        },
        {
          label: "Max Drawdown",
          value: formatPct(-Math.abs(result.metrics.max_drawdown_pct)),
          tone: "loss",
        },
        {
          label: "Win Rate",
          value: `${(result.metrics.win_rate * 100).toFixed(1)}%`,
        },
        {
          label: "Total Trades",
          value: result.metrics.total_trades.toString(),
        },
        {
          label: "Profit Factor",
          value: result.metrics.profit_factor.toFixed(2),
          trend: result.metrics.profit_factor - 1,
        },
        {
          label: "Avg Trade P&L",
          value: formatCurrency(result.metrics.avg_trade_pnl),
          trend: result.metrics.avg_trade_pnl,
        },
        {
          label: "Best Trade",
          value: formatCurrency(result.metrics.best_trade_pnl),
          tone: "profit",
        },
        {
          label: "Worst Trade",
          value: formatCurrency(result.metrics.worst_trade_pnl),
          tone: "loss",
        },
        {
          label: "Sortino Ratio",
          value: result.metrics.sortino_ratio?.toFixed(2) ?? "—",
        },
        {
          label: "Calmar Ratio",
          value: result.metrics.calmar_ratio?.toFixed(2) ?? "—",
        },
        {
          label: "Deflated Sharpe",
          value: result.metrics.deflated_sharpe_ratio?.toFixed(2) ?? "—",
        },
        {
          label: "DD Duration",
          value:
            result.metrics.max_drawdown_duration_bars != null
              ? `${result.metrics.max_drawdown_duration_bars} bars`
              : "—",
        },
      ]
    : [];

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-col gap-6">
        <PageHeader
          eyebrow="Strategy"
          title="Backtest"
          description="Configure a strategy, replay history, and inspect risk-adjusted returns."
          actions={
            <Button onClick={handleRun} disabled={running} size="sm">
              <Play className="mr-1.5 size-3.5" />
              {running ? "Running…" : "Run backtest"}
            </Button>
          }
        />

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          {/* Configuration Panel */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle>Configuration</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 pt-4">
              {/* Quick Presets */}
              <div className="space-y-2">
                <Label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  Quick presets
                </Label>
                <div className="grid grid-cols-3 gap-1.5">
                  {PRESETS.map((p) => (
                    <Button
                      key={p.label}
                      variant="outline"
                      size="sm"
                      onClick={() => applyPreset(p)}
                      className="text-xs"
                    >
                      <p.icon className="mr-1 size-3" />
                      {p.label}
                    </Button>
                  ))}
                </div>
              </div>

              <Separator />

              <div className="space-y-1.5">
                <Label>Ticker</Label>
                <Input
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="e.g. AAPL"
                  className="font-mono tabular-nums"
                />
              </div>

              <div className="space-y-1.5">
                <Label>Strategy</Label>
                {strategiesLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : (
                  <Select
                    value={selectedStrategy}
                    onValueChange={handleStrategyChange}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select strategy" />
                    </SelectTrigger>
                    <SelectContent>
                      {strategies?.map((s) => (
                        <SelectItem key={s.name} value={s.name}>
                          {s.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                {currentStrategy && (
                  <p className="text-xs text-muted-foreground">
                    {currentStrategy.description}
                  </p>
                )}
              </div>

              {/* Strategy Education */}
              {eduDescription && (
                <div className="rounded-md border border-border bg-muted/30 p-3">
                  <button
                    type="button"
                    onClick={() => setEduExpanded(!eduExpanded)}
                    className="flex w-full items-center justify-between text-left"
                  >
                    <span className="flex items-center gap-2 text-xs font-medium text-foreground">
                      <Info className="size-3.5" />
                      How does this strategy work?
                    </span>
                    {eduExpanded ? (
                      <ChevronUp className="size-3.5 text-muted-foreground" />
                    ) : (
                      <ChevronDown className="size-3.5 text-muted-foreground" />
                    )}
                  </button>
                  {eduExpanded && (
                    <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                      {eduDescription}
                    </p>
                  )}
                </div>
              )}

              {/* Dynamic Strategy Params */}
              {currentStrategy &&
                Object.keys(currentStrategy.default_params).length > 0 && (
                  <>
                    <Separator />
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                      Parameters
                    </p>
                    {Object.entries(currentStrategy.default_params).map(
                      ([key, defaultVal]) => (
                        <div key={key} className="space-y-1">
                          <Label className="flex items-center gap-1.5 text-xs">
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
                            className="font-mono tabular-nums"
                          />
                        </div>
                      )
                    )}
                  </>
                )}

              <Separator />

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

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label>ATR stop multiplier</Label>
                  <span className="text-xs text-muted-foreground">Optional</span>
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
                  className="font-mono tabular-nums"
                />
                <p className="text-xs text-muted-foreground">
                  Dynamic trailing stop based on Average True Range volatility.
                </p>
              </div>

              <Button
                onClick={handleRun}
                disabled={running}
                className="w-full"
              >
                <Play className="mr-1.5 size-3.5" />
                {running ? "Running…" : "Run backtest"}
              </Button>
            </CardContent>
          </Card>

          {/* Results Panel */}
          <Card className="lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between border-b">
              <CardTitle>Results</CardTitle>
              {result && (
                <a
                  href={api.backtest.exportCsv(result.id)}
                  download
                  className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-muted/50"
                >
                  <Download className="size-3.5" />
                  Export CSV
                </a>
              )}
            </CardHeader>
            <CardContent className="pt-4">
              {!result ? (
                <div className="space-y-3 py-2">
                  <Skeleton className="h-8 w-1/3" />
                  <Skeleton className="h-[280px] w-full" />
                  <p className="pt-2 text-center text-xs text-muted-foreground">
                    Configure and run a backtest to see results.
                  </p>
                </div>
              ) : (
                <Tabs defaultValue="equity">
                  <TabsList>
                    <TabsTrigger value="equity">Equity</TabsTrigger>
                    <TabsTrigger value="trades">Trades</TabsTrigger>
                    <TabsTrigger value="metrics">Metrics</TabsTrigger>
                  </TabsList>

                  <TabsContent value="equity" className="mt-4">
                    <div className="h-[320px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          data={equityCurveData}
                          margin={{ top: 6, right: 6, left: 0, bottom: 0 }}
                        >
                          <defs>
                            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.18} />
                              <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
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
                            formatter={(value) => [
                              formatCurrency(Number(value)),
                              "Portfolio",
                            ]}
                          />
                          <Line
                            type="monotone"
                            dataKey="value"
                            stroke="var(--primary)"
                            strokeWidth={1.5}
                            dot={false}
                            fill="url(#equityGrad)"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </TabsContent>

                  <TabsContent value="trades" className="mt-4">
                    {result.trades.length === 0 ? (
                      <p className="py-8 text-center text-sm text-muted-foreground">
                        No trades
                      </p>
                    ) : (
                      <div className="max-h-[400px] overflow-y-auto">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Date</TableHead>
                              <TableHead>Side</TableHead>
                              <TableHead className="text-right">Price</TableHead>
                              <TableHead className="text-right">Qty</TableHead>
                              <TableHead className="text-right">Value</TableHead>
                              <TableHead className="text-right">P&amp;L</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {result.trades.map((trade, i) => {
                              const isBuy = trade.side.toUpperCase() === "BUY";
                              return (
                                <TableRow key={i}>
                                  <TableCell className="font-mono tabular-nums text-xs text-muted-foreground">
                                    {new Date(trade.date).toLocaleDateString()}
                                  </TableCell>
                                  <TableCell>
                                    <span
                                      className={cn(
                                        "font-mono text-[10.5px] uppercase tracking-wider",
                                        isBuy ? "text-profit" : "text-loss",
                                      )}
                                    >
                                      {trade.side.toUpperCase()}
                                    </span>
                                  </TableCell>
                                  <TableCell className="text-right font-mono tabular-nums">
                                    {formatCurrency(trade.price)}
                                  </TableCell>
                                  <TableCell className="text-right font-mono tabular-nums">
                                    {trade.quantity}
                                  </TableCell>
                                  <TableCell className="text-right font-mono tabular-nums">
                                    {formatCurrency(trade.value)}
                                  </TableCell>
                                  <TableCell
                                    className={cn(
                                      "text-right font-mono tabular-nums",
                                      trade.pnl > 0 && "text-profit",
                                      trade.pnl < 0 && "text-loss",
                                    )}
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
                        <Badge
                          variant="outline"
                          className={cn(
                            "border-border font-mono text-[10.5px] uppercase tracking-wider",
                            riskLevel.tone === "profit" && "text-profit",
                            riskLevel.tone === "loss" && "text-loss",
                            riskLevel.tone === "neutral" && "text-muted-foreground",
                          )}
                        >
                          {riskLevel.label}
                        </Badge>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3 lg:grid-cols-4">
                      {statRows.map((m) => (
                        <div key={m.label} className="bg-card p-4">
                          <Stat
                            label={m.label}
                            value={
                              <span
                                className={cn(
                                  m.tone === "profit" && "text-profit",
                                  m.tone === "loss" && "text-loss",
                                )}
                              >
                                {m.value}
                              </span>
                            }
                            trend={m.trend ?? null}
                            sub={
                              METRIC_TOOLTIPS[m.label] ? undefined : undefined
                            }
                          />
                          {METRIC_TOOLTIPS[m.label] && (
                            <div className="mt-1 flex items-center gap-1 text-[10px] text-muted-foreground">
                              <InfoTip text={METRIC_TOOLTIPS[m.label]} />
                              <span className="truncate">info</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </TabsContent>
                </Tabs>
              )}

              {result && (
                <div className="mt-4 rounded-md border border-border bg-muted/20 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        Statistical significance
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Bootstrap CI on Sharpe + permutation test vs. shuffled returns.
                      </p>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleSignificance}
                      disabled={sigRunning}
                    >
                      {sigRunning ? "Running…" : "Run test"}
                    </Button>
                  </div>
                  {significance && (
                    <div className="mt-4 grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3">
                      <div className="bg-card p-4">
                        <Stat
                          label="Sharpe (point)"
                          value={significance.bootstrap_ci.point_estimate.toFixed(2)}
                        />
                      </div>
                      <div className="bg-card p-4">
                        <Stat
                          label={`${(significance.bootstrap_ci.confidence * 100).toFixed(0)}% CI`}
                          value={`[${significance.bootstrap_ci.ci_low.toFixed(2)}, ${significance.bootstrap_ci.ci_high.toFixed(2)}]`}
                        />
                      </div>
                      <div className="bg-card p-4">
                        <Stat
                          label="Permutation p-value"
                          value={
                            <span
                              className={
                                significance.permutation.p_value < 0.05
                                  ? "text-profit"
                                  : undefined
                              }
                            >
                              {significance.permutation.p_value.toFixed(3)}
                            </span>
                          }
                          sub={
                            significance.permutation.p_value < 0.05
                              ? "Significant at α=0.05"
                              : "Not significant"
                          }
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Previous Results */}
        <Card>
          <CardHeader className="border-b">
            <CardTitle>Previous runs</CardTitle>
          </CardHeader>
          <CardContent className="px-0 pt-0">
            {historyLoading ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
                <Skeleton className="h-9 w-full" />
              </div>
            ) : !previousResults || previousResults.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No previous backtests
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-4">Ticker</TableHead>
                    <TableHead>Strategy</TableHead>
                    <TableHead className="text-right">Return</TableHead>
                    <TableHead className="text-right">Sharpe</TableHead>
                    <TableHead className="text-right">Max DD</TableHead>
                    <TableHead className="text-right">Trades</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="w-10 pr-4" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {previousResults.map((r) => (
                    <TableRow
                      key={r.id}
                      className="cursor-pointer"
                      onClick={() => setResult(r)}
                    >
                      <TableCell className="pl-4 font-mono font-medium tabular-nums">
                        {r.ticker}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {r.strategy_type}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-mono tabular-nums",
                          r.metrics.total_return_pct >= 0 ? "text-profit" : "text-loss",
                        )}
                      >
                        {formatPct(r.metrics.total_return_pct)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {r.metrics.sharpe_ratio.toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-loss">
                        {formatPct(-Math.abs(r.metrics.max_drawdown_pct))}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {r.metrics.total_trades}
                      </TableCell>
                      <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                        {new Date(r.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="pr-4">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(r.id);
                          }}
                          className="text-muted-foreground hover:text-loss"
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
