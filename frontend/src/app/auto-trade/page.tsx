"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Bot,
  Loader2,
  Play,
  Search,
  TrendingUp,
  TrendingDown,
  Minus,
  Zap,
  ShieldCheck,
  AlertTriangle,
  Clock,
  Square,
  Timer,
  Scale,
} from "lucide-react";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import type {
  AutoTradeResult,
  AutoTradeAnalysis,
  SchedulerStatus,
  RebalanceResult,
} from "@/lib/api";

function signalBadge(signal: string) {
  switch (signal) {
    case "strong_buy":
      return <Badge className="bg-green-600 text-white">Strong Buy</Badge>;
    case "buy":
      return <Badge className="bg-green-500/20 text-green-400">Buy</Badge>;
    case "strong_sell":
      return <Badge className="bg-red-600 text-white">Strong Sell</Badge>;
    case "sell":
      return <Badge className="bg-red-500/20 text-red-400">Sell</Badge>;
    case "hold":
      return <Badge className="bg-zinc-700 text-zinc-300">Hold</Badge>;
    default:
      return <Badge className="bg-zinc-800 text-zinc-500">{signal}</Badge>;
  }
}

function confidenceBar(confidence: number) {
  const pct = Math.round(confidence * 100);
  const color =
    pct > 60 ? "bg-green-500" : pct > 30 ? "bg-yellow-500" : "bg-zinc-600";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-zinc-800">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-zinc-400">{pct}%</span>
    </div>
  );
}

function actionIcon(action: string) {
  switch (action) {
    case "buy":
      return <TrendingUp className="size-4 text-green-500" />;
    case "sell":
      return <TrendingDown className="size-4 text-red-500" />;
    default:
      return <Minus className="size-4 text-zinc-500" />;
  }
}

export default function AutoTradePage() {
  const [analyzing, setAnalyzing] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [analysis, setAnalysis] = useState<AutoTradeAnalysis | null>(null);
  const [result, setResult] = useState<AutoTradeResult | null>(null);
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [schedulerLoading, setSchedulerLoading] = useState(false);
  const [selectedInterval, setSelectedInterval] = useState(30);
  const [rebalancing, setRebalancing] = useState(false);
  const [rebalanceResult, setRebalanceResult] = useState<RebalanceResult | null>(null);

  const fetchSchedulerStatus = useCallback(async () => {
    try {
      const status = await api.autoTrade.schedulerStatus();
      setSchedulerStatus(status);
      if (status.interval_minutes) {
        setSelectedInterval(status.interval_minutes);
      }
    } catch {
      // Silently fail on status poll
    }
  }, []);

  useEffect(() => {
    fetchSchedulerStatus();
    const interval = setInterval(fetchSchedulerStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchSchedulerStatus]);

  async function handleAnalyze() {
    setAnalyzing(true);
    setResult(null);
    try {
      const res = await api.autoTrade.analyze();
      setAnalysis(res);
      toast.success("Analysis complete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleExecute() {
    setExecuting(true);
    try {
      const res = await api.autoTrade.run();
      setResult(res);
      setAnalysis(null);
      toast.success("Auto-trade cycle complete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Auto-trade failed");
    } finally {
      setExecuting(false);
    }
  }

  async function handleSchedulerToggle() {
    setSchedulerLoading(true);
    try {
      if (schedulerStatus?.running) {
        const status = await api.autoTrade.schedulerStop();
        setSchedulerStatus(status);
        toast.success("Scheduled trading stopped");
      } else {
        const status = await api.autoTrade.schedulerStart(selectedInterval);
        setSchedulerStatus(status);
        toast.success(`Scheduled trading started (every ${selectedInterval}m)`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Scheduler action failed");
    } finally {
      setSchedulerLoading(false);
    }
  }

  async function handleRebalance() {
    setRebalancing(true);
    try {
      const res = await api.autoTrade.rebalance();
      setRebalanceResult(res);
      if (res.error) {
        toast.error(res.error);
      } else {
        toast.success("Portfolio rebalanced");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Rebalance failed");
    } finally {
      setRebalancing(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="size-6 text-purple-500" />
          <h1 className="text-2xl font-bold text-zinc-100">
            AI Auto-Trader
          </h1>
          <Badge variant="outline" className="border-purple-500/40 text-purple-400">
            Beta
          </Badge>
        </div>
      </div>

      {/* Controls */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="text-zinc-100">Autonomous Trading</CardTitle>
          <CardDescription className="text-zinc-500">
            AI analyzes sentiment + technicals across your watchlist and
            autonomously places paper trades based on its analysis.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3 rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3">
            <AlertTriangle className="size-5 shrink-0 text-yellow-500" />
            <p className="text-sm text-yellow-200">
              Paper trading only — no real money is involved. The AI will
              analyze your watchlist tickers and execute trades on your virtual
              portfolio.
            </p>
          </div>

          <div className="flex gap-3">
            <Button
              onClick={handleAnalyze}
              disabled={analyzing || executing}
              variant="outline"
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              {analyzing ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Search className="mr-2 size-4" />
              )}
              Analyze Only
            </Button>
            <Button
              onClick={handleExecute}
              disabled={analyzing || executing}
              className="bg-purple-600 text-white hover:bg-purple-700"
            >
              {executing ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Zap className="mr-2 size-4" />
              )}
              Analyze & Execute Trades
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Scheduled Trading */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-zinc-100">
            <Clock className="size-5 text-purple-400" />
            Scheduled Trading
          </CardTitle>
          <CardDescription className="text-zinc-500">
            Automatically run trading cycles at regular intervals during US
            market hours (9:30 AM – 4:00 PM Eastern, weekdays).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-sm text-zinc-400">Interval:</label>
              <select
                value={selectedInterval}
                onChange={(e) => setSelectedInterval(Number(e.target.value))}
                disabled={schedulerStatus?.running || schedulerLoading}
                className="rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 focus:border-purple-500 focus:outline-none disabled:opacity-50"
              >
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={60}>60 minutes</option>
              </select>
            </div>

            <Button
              onClick={handleSchedulerToggle}
              disabled={schedulerLoading}
              className={
                schedulerStatus?.running
                  ? "bg-red-600 text-white hover:bg-red-700"
                  : "bg-purple-600 text-white hover:bg-purple-700"
              }
            >
              {schedulerLoading ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : schedulerStatus?.running ? (
                <Square className="mr-2 size-4" />
              ) : (
                <Play className="mr-2 size-4" />
              )}
              {schedulerStatus?.running ? "Stop Scheduler" : "Start Scheduler"}
            </Button>
          </div>

          {/* Status display */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <p className="text-xs text-zinc-500">Status</p>
              <div className="mt-1 flex items-center gap-2">
                <span
                  className={`size-2 rounded-full ${
                    schedulerStatus?.running ? "bg-green-500 animate-pulse" : "bg-zinc-600"
                  }`}
                />
                <span className="text-sm font-medium text-zinc-200">
                  {schedulerStatus?.running ? "Running" : "Stopped"}
                </span>
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <p className="text-xs text-zinc-500">Interval</p>
              <p className="mt-1 text-sm font-medium text-zinc-200">
                {schedulerStatus?.interval_minutes ?? selectedInterval}m
              </p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <p className="text-xs text-zinc-500">Next Run</p>
              <p className="mt-1 text-sm font-medium text-zinc-200">
                {schedulerStatus?.next_run
                  ? new Date(schedulerStatus.next_run).toLocaleTimeString()
                  : "—"}
              </p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
              <p className="text-xs text-zinc-500">Cycles Completed</p>
              <p className="mt-1 text-sm font-medium text-zinc-200">
                {schedulerStatus?.total_cycles ?? 0}
              </p>
            </div>
          </div>

          {/* Last run */}
          {schedulerStatus?.last_run && (
            <p className="text-xs text-zinc-500">
              <Timer className="mr-1 inline size-3" />
              Last run: {new Date(schedulerStatus.last_run).toLocaleString()}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Portfolio Rebalancing */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-zinc-100">
            <Scale className="size-5 text-cyan-400" />
            Portfolio Rebalancing
          </CardTitle>
          <CardDescription className="text-zinc-500">
            Equal-weight rebalance across all held positions. Positions
            deviating more than 5% from target are adjusted.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            onClick={handleRebalance}
            disabled={rebalancing || executing}
            className="bg-cyan-600 text-white hover:bg-cyan-700"
          >
            {rebalancing ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Scale className="mr-2 size-4" />
            )}
            Rebalance Portfolio
          </Button>

          {rebalanceResult && !rebalanceResult.error && (
            <div className="space-y-4">
              {/* Weight comparison table */}
              {Object.keys(rebalanceResult.before).length > 0 && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
                  <p className="mb-3 text-sm font-medium text-zinc-300">
                    Position Weights
                  </p>
                  <div className="space-y-2">
                    <div className="grid grid-cols-4 gap-2 text-xs font-medium text-zinc-500">
                      <span>Ticker</span>
                      <span className="text-right">Before</span>
                      <span className="text-right">After</span>
                      <span className="text-right">Target</span>
                    </div>
                    {Object.keys(rebalanceResult.before).map((ticker) => {
                      const before = rebalanceResult.before[ticker] ?? 0;
                      const after = rebalanceResult.after[ticker] ?? 0;
                      const target =
                        Object.keys(rebalanceResult.before).length > 0
                          ? 1 / Object.keys(rebalanceResult.before).length
                          : 0;
                      return (
                        <div
                          key={ticker}
                          className="grid grid-cols-4 gap-2 text-sm"
                        >
                          <span className="font-mono text-blue-400">
                            {ticker}
                          </span>
                          <span className="text-right text-zinc-400">
                            {(before * 100).toFixed(1)}%
                          </span>
                          <span className="text-right text-zinc-200">
                            {(after * 100).toFixed(1)}%
                          </span>
                          <span className="text-right text-zinc-500">
                            {(target * 100).toFixed(1)}%
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-4">
                <p className="mb-2 text-sm font-medium text-zinc-300">
                  Rebalance Actions
                </p>
                <div className="space-y-1">
                  {rebalanceResult.rebalance_actions.map((action, i) => (
                    <p key={i} className="text-xs text-zinc-400">
                      {action.startsWith("SELL") ? (
                        <TrendingDown className="mr-1 inline size-3 text-red-400" />
                      ) : action.startsWith("BUY") ? (
                        <TrendingUp className="mr-1 inline size-3 text-green-400" />
                      ) : (
                        <Minus className="mr-1 inline size-3 text-zinc-500" />
                      )}
                      {action}
                    </p>
                  ))}
                </div>
              </div>

              {/* Portfolio summary */}
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                  <p className="text-xs text-zinc-500">Portfolio Value</p>
                  <p className="text-sm font-bold text-zinc-100">
                    $
                    {rebalanceResult.portfolio.total_value.toLocaleString(
                      undefined,
                      { maximumFractionDigits: 0 }
                    )}
                  </p>
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                  <p className="text-xs text-zinc-500">Cash</p>
                  <p className="text-sm font-bold text-zinc-100">
                    $
                    {rebalanceResult.portfolio.cash.toLocaleString(undefined, {
                      maximumFractionDigits: 0,
                    })}
                  </p>
                </div>
                <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                  <p className="text-xs text-zinc-500">Positions</p>
                  <p className="text-sm font-bold text-zinc-100">
                    {rebalanceResult.portfolio.positions_count}
                  </p>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {analysis && (
        <Card className="border-zinc-800 bg-zinc-900">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-zinc-100">
              <Search className="size-5 text-blue-500" />
              Analysis Results
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="max-h-[500px]">
              <div className="space-y-3">
                {analysis.analyses.map((a) => (
                  <div
                    key={a.ticker}
                    className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 p-4"
                  >
                    <div className="flex items-center gap-4">
                      <span className="font-mono text-lg font-bold text-blue-400">
                        {a.ticker}
                      </span>
                      {signalBadge(a.signal)}
                      {a.weekly_trend && a.weekly_trend !== "neutral" && (
                        <Badge
                          className={
                            a.weekly_trend === "bullish"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : "bg-orange-500/20 text-orange-400"
                          }
                        >
                          {a.weekly_trend === "bullish" ? (
                            <TrendingUp className="mr-1 size-3" />
                          ) : (
                            <TrendingDown className="mr-1 size-3" />
                          )}
                          Weekly {a.weekly_trend}
                        </Badge>
                      )}
                      {a.bollinger_squeeze && (
                        <Badge className="bg-yellow-500/20 text-yellow-400">
                          <Zap className="mr-1 size-3" />
                          Squeeze
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-6">
                      {a.price != null && (
                        <div className="text-right">
                          <p className="text-xs text-zinc-500">Price</p>
                          <p className="font-mono text-zinc-200">
                            ${a.price?.toFixed(2)}
                          </p>
                        </div>
                      )}
                      {a.sentiment_score != null && (
                        <div className="text-right">
                          <p className="text-xs text-zinc-500">Sentiment</p>
                          <p
                            className={`font-mono ${
                              a.sentiment_score > 0
                                ? "text-green-400"
                                : a.sentiment_score < 0
                                  ? "text-red-400"
                                  : "text-zinc-400"
                            }`}
                          >
                            {a.sentiment_score > 0 ? "+" : ""}
                            {a.sentiment_score?.toFixed(2)}
                          </p>
                        </div>
                      )}
                      {a.rsi != null && (
                        <div className="text-right">
                          <p className="text-xs text-zinc-500">RSI</p>
                          <p className="font-mono text-zinc-200">
                            {a.rsi?.toFixed(0)}
                          </p>
                        </div>
                      )}
                      {a.macd_histogram != null && (
                        <div className="text-right">
                          <p className="text-xs text-zinc-500">MACD Hist</p>
                          <p
                            className={`font-mono ${
                              a.macd_histogram > 0
                                ? "text-green-400"
                                : a.macd_histogram < 0
                                  ? "text-red-400"
                                  : "text-zinc-400"
                            }`}
                          >
                            {a.macd_histogram > 0 ? "+" : ""}
                            {a.macd_histogram?.toFixed(3)}
                          </p>
                        </div>
                      )}
                      <div>
                        <p className="text-xs text-zinc-500">Confidence</p>
                        {confidenceBar(a.confidence)}
                      </div>
                    </div>
                  </div>
                ))}
                {analysis.analyses.length > 0 && (
                  <div className="mt-2 space-y-1 rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
                    <p className="text-xs font-medium text-zinc-400">Reasons</p>
                    {analysis.analyses.map((a) =>
                      a.reasons.map((r, i) => (
                        <p key={`${a.ticker}-${i}`} className="text-xs text-zinc-500">
                          <span className="font-mono text-blue-400">{a.ticker}</span>{" "}
                          — {r}
                        </p>
                      ))
                    )}
                  </div>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Execution Results */}
      {result && (
        <>
          {/* Portfolio Summary */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Card className="border-zinc-800 bg-zinc-900">
              <CardContent className="pt-4">
                <p className="text-xs text-zinc-500">Portfolio Value</p>
                <p className="text-xl font-bold text-zinc-100">
                  ${result.portfolio.total_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </CardContent>
            </Card>
            <Card className="border-zinc-800 bg-zinc-900">
              <CardContent className="pt-4">
                <p className="text-xs text-zinc-500">Cash</p>
                <p className="text-xl font-bold text-zinc-100">
                  ${result.portfolio.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </CardContent>
            </Card>
            <Card className="border-zinc-800 bg-zinc-900">
              <CardContent className="pt-4">
                <p className="text-xs text-zinc-500">Total P&L</p>
                <p
                  className={`text-xl font-bold ${
                    result.portfolio.total_pnl >= 0
                      ? "text-green-500"
                      : "text-red-500"
                  }`}
                >
                  {result.portfolio.total_pnl >= 0 ? "+" : ""}$
                  {result.portfolio.total_pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </CardContent>
            </Card>
            <Card className="border-zinc-800 bg-zinc-900">
              <CardContent className="pt-4">
                <p className="text-xs text-zinc-500">Positions</p>
                <p className="text-xl font-bold text-zinc-100">
                  {result.portfolio.positions_count}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Decisions & Executions */}
          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-zinc-100">
                <ShieldCheck className="size-5 text-green-500" />
                Trade Decisions & Executions
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="max-h-[400px]">
                <div className="space-y-2">
                  {result.decisions.map((d, i) => {
                    const exec = result.executions[i];
                    return (
                      <div
                        key={d.ticker}
                        className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 p-4"
                      >
                        <div className="flex items-center gap-3">
                          {actionIcon(d.action)}
                          <span className="font-mono font-bold text-blue-400">
                            {d.ticker}
                          </span>
                          <Badge
                            className={
                              d.action === "buy"
                                ? "bg-green-500/20 text-green-400"
                                : d.action === "sell"
                                  ? "bg-red-500/20 text-red-400"
                                  : "bg-zinc-700 text-zinc-400"
                            }
                          >
                            {d.action.toUpperCase()}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-6 text-sm">
                          {d.quantity > 0 && (
                            <span className="text-zinc-400">
                              {d.quantity} shares @ ${d.price.toFixed(2)}
                            </span>
                          )}
                          {confidenceBar(d.confidence)}
                          {exec && (
                            <Badge
                              variant="outline"
                              className={
                                exec.status === "filled"
                                  ? "border-green-500/40 text-green-400"
                                  : exec.status === "skipped"
                                    ? "border-zinc-600 text-zinc-500"
                                    : "border-red-500/40 text-red-400"
                              }
                            >
                              {exec.status}
                            </Badge>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>

              <Separator className="my-4 bg-zinc-800" />

              <div className="space-y-1">
                <p className="text-xs font-medium text-zinc-400">AI Reasoning</p>
                {result.decisions.map((d) =>
                  d.reasons.map((r, i) => (
                    <p key={`${d.ticker}-${i}`} className="text-xs text-zinc-500">
                      <span className="font-mono text-blue-400">{d.ticker}</span> — {r}
                    </p>
                  ))
                )}
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Empty state */}
      {!analysis && !result && (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <Bot className="mb-3 size-12 text-purple-500/50" />
          <p className="text-lg">AI Auto-Trader</p>
          <p className="mt-1 max-w-md text-center text-sm text-zinc-600">
            Add tickers to your watchlist in Settings, then click
            &quot;Analyze &amp; Execute Trades&quot; to let the AI make autonomous
            trading decisions based on sentiment and technical analysis.
          </p>
        </div>
      )}
    </div>
  );
}
