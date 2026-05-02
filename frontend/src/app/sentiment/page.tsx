"use client";

import { useState, useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { Search, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/ui/stat";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type { SentimentResult } from "@/lib/api";
import { cn } from "@/lib/utils";

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function scoreClass(score: number) {
  if (score > 0.15) return "text-profit";
  if (score < -0.15) return "text-loss";
  return "text-muted-foreground";
}

function scoreDot(score: number) {
  if (score > 0.15) return "bg-profit";
  if (score < -0.15) return "bg-loss";
  return "bg-muted-foreground/60";
}

function sentimentLabel(score: number) {
  if (score > 0.15) return "Bullish";
  if (score < -0.15) return "Bearish";
  return "Neutral";
}

function SentimentGauge({ score }: { score: number }) {
  // score from -1.0 to +1.0, map to 0–100%
  const pct = ((score + 1) / 2) * 100;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between text-[11px] uppercase tracking-wider text-muted-foreground">
        <span>Bearish</span>
        <span
          className={cn(
            "font-mono text-2xl tabular-nums normal-case tracking-normal",
            scoreClass(score),
          )}
        >
          {score >= 0 ? "+" : ""}
          {score.toFixed(3)}
        </span>
        <span>Bullish</span>
      </div>
      <div className="relative h-1.5 w-full overflow-hidden rounded-sm border border-border bg-muted">
        <div
          className="absolute top-0 h-full w-px -translate-x-1/2 bg-foreground"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between font-mono text-[10px] tabular-nums text-muted-foreground">
        <span>-1.0</span>
        <span>0</span>
        <span>+1.0</span>
      </div>
    </div>
  );
}

export default function SentimentPage() {
  const [ticker, setTicker] = useState("");
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<SentimentResult | null>(null);
  const [historyTicker, setHistoryTicker] = useState<string | null>(null);

  const {
    data: historyData,
    loading: historyLoading,
  } = useFetch(
    () => (historyTicker ? api.sentiment.history(historyTicker).then((r) => r.items) : Promise.resolve([])),
    [historyTicker]
  );

  const chartData = useMemo(() => {
    if (!historyData) return [];
    return historyData.map((d) => ({
      date: new Date(d.date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      }),
      score: d.score,
    }));
  }, [historyData]);

  async function handleAnalyze() {
    const t = ticker.trim().toUpperCase();
    if (!t) {
      toast.error("Please enter a ticker");
      return;
    }

    setAnalyzing(true);
    try {
      const res = await api.sentiment.analyze(t);
      setResult(res);
      setHistoryTicker(t);
      toast.success(`Sentiment analysis for ${t} complete`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  const trendIcon =
    result?.trend === "improving" ? (
      <TrendingUp className="size-3.5" />
    ) : result?.trend === "declining" ? (
      <TrendingDown className="size-3.5" />
    ) : (
      <Minus className="size-3.5" />
    );

  const trendClass =
    result?.trend === "improving"
      ? "text-profit border-profit/40"
      : result?.trend === "declining"
        ? "text-loss border-loss/40"
        : "text-muted-foreground border-border";

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Market"
        title="Sentiment analysis"
        description="Aggregated news scoring with VADER + LLM, plus historical trend."
        actions={
          <div className="flex items-end gap-2">
            <Input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
              placeholder="Ticker (e.g. AAPL)"
              className="w-40 font-mono tabular-nums"
            />
            <Button onClick={handleAnalyze} disabled={analyzing} size="sm">
              <Search className="mr-1.5 size-3.5" />
              {analyzing ? "Analyzing…" : "Analyze"}
            </Button>
          </div>
        }
      />

      {!result ? (
        <Card>
          <CardContent className="py-10">
            <div className="space-y-3">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-32 w-full" />
              <p className="pt-2 text-center text-xs text-muted-foreground">
                Enter a ticker to analyze market sentiment.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Sentiment Overview */}
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader className="flex flex-row items-center justify-between border-b">
                <CardTitle className="flex items-baseline gap-2">
                  <span className="font-mono tabular-nums text-foreground">
                    {result.ticker}
                  </span>
                  <span className="text-muted-foreground">sentiment</span>
                </CardTitle>
                <Badge
                  variant="outline"
                  className={cn(
                    "font-mono text-[10.5px] uppercase tracking-wider",
                    trendClass,
                  )}
                >
                  {trendIcon}
                  <span className="ml-1">{result.trend}</span>
                </Badge>
              </CardHeader>
              <CardContent className="space-y-5 pt-4">
                <SentimentGauge score={result.overall_score} />

                <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border">
                  <div className="bg-card p-3">
                    <Stat
                      label="VADER average"
                      value={
                        <span className={scoreClass(result.vader_avg)}>
                          {result.vader_avg.toFixed(3)}
                        </span>
                      }
                    />
                  </div>
                  <div className="bg-card p-3">
                    <Stat
                      label="LLM score"
                      value={
                        result.llm_score !== null ? (
                          <span className={scoreClass(result.llm_score)}>
                            {result.llm_score.toFixed(3)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">N/A</span>
                        )
                      }
                    />
                  </div>
                </div>

                <div className="flex items-center gap-4 font-mono text-[11px] tabular-nums text-muted-foreground">
                  <span>{result.num_sources} sources</span>
                  <span>·</span>
                  <span>Updated {timeAgo(result.updated_at)}</span>
                </div>
              </CardContent>
            </Card>

            {/* Score Summary */}
            <Card>
              <CardHeader className="border-b">
                <CardTitle>Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pt-4">
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    Overall score
                  </p>
                  <p
                    className={cn(
                      "mt-1 font-mono text-4xl font-medium tabular-nums",
                      scoreClass(result.overall_score),
                    )}
                  >
                    {result.overall_score >= 0 ? "+" : ""}
                    {result.overall_score.toFixed(2)}
                  </p>
                </div>

                <div className="space-y-2 border-t border-border pt-3 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Sentiment</span>
                    <span
                      className={cn("font-medium", scoreClass(result.overall_score))}
                    >
                      {sentimentLabel(result.overall_score)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Trend</span>
                    <span
                      className={cn(
                        "font-medium capitalize",
                        result.trend === "improving" && "text-profit",
                        result.trend === "declining" && "text-loss",
                      )}
                    >
                      {result.trend}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Sources</span>
                    <span className="font-mono tabular-nums text-foreground">
                      {result.num_sources}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* News Feed */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle>Headlines</CardTitle>
            </CardHeader>
            <CardContent className="pt-2">
              {result.headlines.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No headlines available
                </p>
              ) : (
                <ScrollArea className="h-[400px]">
                  <div className="divide-y divide-border">
                    {result.headlines.map((item, i) => (
                      <a
                        key={i}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-start gap-3 px-2 py-3 transition-colors hover:bg-muted/40"
                      >
                        <div
                          className={cn(
                            "mt-1.5 size-2 shrink-0 rounded-full",
                            scoreDot(item.score),
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm leading-snug text-foreground">
                            {item.headline}
                          </p>
                          <div className="mt-1 flex items-center gap-2 font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
                            <span>{item.source}</span>
                            <span>·</span>
                            <span>{timeAgo(item.published_at)}</span>
                          </div>
                        </div>
                        <span
                          className={cn(
                            "shrink-0 font-mono text-xs tabular-nums",
                            scoreClass(item.score),
                          )}
                        >
                          {item.score >= 0 ? "+" : ""}
                          {item.score.toFixed(2)}
                        </span>
                      </a>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* History Chart */}
          <Card>
            <CardHeader className="border-b">
              <CardTitle>
                Sentiment history ·{" "}
                <span className="font-mono tabular-nums">{result.ticker}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-3">
              {historyLoading ? (
                <Skeleton className="h-[250px] w-full" />
              ) : chartData.length === 0 ? (
                <p className="py-12 text-center text-sm text-muted-foreground">
                  No historical data available
                </p>
              ) : (
                <div className="h-[250px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={chartData}
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
                          fontSize: 11,
                          fontFamily: "var(--font-mono)",
                        }}
                        axisLine={{ stroke: "var(--border)" }}
                        tickLine={false}
                      />
                      <YAxis
                        domain={[-1, 1]}
                        ticks={[-1, -0.5, 0, 0.5, 1]}
                        tick={{
                          fill: "var(--muted-foreground)",
                          fontSize: 11,
                          fontFamily: "var(--font-mono)",
                        }}
                        axisLine={{ stroke: "var(--border)" }}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "var(--popover)",
                          border: "1px solid var(--border)",
                          borderRadius: "0.375rem",
                          color: "var(--popover-foreground)",
                          fontSize: 12,
                          fontFamily: "var(--font-mono)",
                        }}
                        formatter={(value) => [Number(value).toFixed(3), "Score"]}
                      />
                      <ReferenceLine y={0} stroke="var(--border)" strokeWidth={1} />
                      <Line
                        type="monotone"
                        dataKey="score"
                        stroke="var(--primary)"
                        strokeWidth={1.5}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
