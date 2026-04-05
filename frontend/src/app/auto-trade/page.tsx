"use client";

import { useState } from "react";
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

      {/* Analysis Results */}
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
