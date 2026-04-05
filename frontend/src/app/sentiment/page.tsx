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
} from "recharts";
import { Search, Loader2, Newspaper, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import type { SentimentResult } from "@/lib/api";

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function scoreColor(score: number) {
  if (score > 0.15) return "text-green-500";
  if (score < -0.15) return "text-red-500";
  return "text-zinc-400";
}

function scoreDot(score: number) {
  if (score > 0.15) return "bg-green-500";
  if (score < -0.15) return "bg-red-500";
  return "bg-zinc-500";
}

function SentimentGauge({ score }: { score: number }) {
  // score from -1.0 to +1.0, map to 0–100%
  const pct = ((score + 1) / 2) * 100;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-zinc-500">
        <span>Bearish</span>
        <span className="text-lg font-bold text-zinc-100">
          {score >= 0 ? "+" : ""}
          {score.toFixed(3)}
        </span>
        <span>Bullish</span>
      </div>
      <div className="relative h-4 w-full overflow-hidden rounded-full">
        {/* Gradient background */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(to right, #ef4444, #f59e0b, #eab308, #22c55e)",
          }}
        />
        {/* Marker */}
        <div
          className="absolute top-0 h-full w-1 -translate-x-1/2 rounded-sm bg-white shadow-[0_0_6px_rgba(255,255,255,0.8)]"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] text-zinc-600">
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
      <TrendingUp className="size-4" />
    ) : result?.trend === "declining" ? (
      <TrendingDown className="size-4" />
    ) : (
      <Minus className="size-4" />
    );

  const trendColor =
    result?.trend === "improving"
      ? "bg-green-500/20 text-green-400"
      : result?.trend === "declining"
        ? "bg-red-500/20 text-red-400"
        : "bg-zinc-700 text-zinc-300";

  return (
    <div className="flex flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <Newspaper className="size-6 text-blue-500" />
        <h1 className="text-2xl font-bold text-zinc-100">Sentiment Analysis</h1>
      </div>

      {/* Search Bar */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardContent className="pt-6">
          <div className="flex gap-3">
            <Input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
              placeholder="Enter ticker (e.g. AAPL)"
              className="border-zinc-700 bg-zinc-950 font-mono text-zinc-100 placeholder:text-zinc-600"
            />
            <Button
              onClick={handleAnalyze}
              disabled={analyzing}
              className="shrink-0 bg-blue-600 text-white hover:bg-blue-700"
            >
              {analyzing ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <Search className="mr-2 size-4" />
              )}
              Analyze
            </Button>
          </div>
        </CardContent>
      </Card>

      {!result ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <Search className="mb-3 size-10" />
          <p>Enter a ticker to analyze market sentiment</p>
          <p className="mt-1 text-xs text-zinc-600">
            We aggregate news from multiple sources and score sentiment
          </p>
        </div>
      ) : (
        <>
          {/* Sentiment Overview */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <Card className="border-zinc-800 bg-zinc-900 lg:col-span-2">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-zinc-100">
                    <span className="font-mono text-blue-400">{result.ticker}</span>
                    Sentiment
                  </CardTitle>
                  <Badge variant="secondary" className={trendColor}>
                    {trendIcon}
                    <span className="ml-1 capitalize">{result.trend}</span>
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-6">
                <SentimentGauge score={result.overall_score} />

                <Separator className="bg-zinc-800" />

                <div className="grid grid-cols-2 gap-4">
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                    <p className="text-xs text-zinc-500">VADER Average</p>
                    <p className={`mt-1 text-xl font-bold ${scoreColor(result.vader_avg)}`}>
                      {result.vader_avg.toFixed(3)}
                    </p>
                  </div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                    <p className="text-xs text-zinc-500">LLM Score</p>
                    <p
                      className={`mt-1 text-xl font-bold ${
                        result.llm_score !== null
                          ? scoreColor(result.llm_score)
                          : "text-zinc-500"
                      }`}
                    >
                      {result.llm_score !== null ? result.llm_score.toFixed(3) : "N/A"}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs text-zinc-500">
                  <span>{result.num_sources} sources analyzed</span>
                  <span>Updated {timeAgo(result.updated_at)}</span>
                </div>
              </CardContent>
            </Card>

            {/* Score Summary Card */}
            <Card className="border-zinc-800 bg-zinc-900">
              <CardHeader>
                <CardTitle className="text-zinc-100">Score Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center">
                  <p
                    className={`text-5xl font-black ${scoreColor(result.overall_score)}`}
                  >
                    {result.overall_score >= 0 ? "+" : ""}
                    {result.overall_score.toFixed(2)}
                  </p>
                  <p className="mt-2 text-sm text-zinc-500">Overall Score</p>
                </div>

                <Separator className="bg-zinc-800" />

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Sentiment</span>
                    <span className={`font-semibold ${scoreColor(result.overall_score)}`}>
                      {result.overall_score > 0.15
                        ? "Bullish"
                        : result.overall_score < -0.15
                          ? "Bearish"
                          : "Neutral"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Trend</span>
                    <span className={`capitalize font-semibold ${
                      result.trend === "improving"
                        ? "text-green-500"
                        : result.trend === "declining"
                          ? "text-red-500"
                          : "text-zinc-300"
                    }`}>
                      {result.trend}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-zinc-400">Sources</span>
                    <span className="font-semibold text-zinc-100">
                      {result.num_sources}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* News Feed */}
          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader>
              <CardTitle className="text-zinc-100">Headlines</CardTitle>
            </CardHeader>
            <CardContent>
              {result.headlines.length === 0 ? (
                <p className="py-8 text-center text-sm text-zinc-500">
                  No headlines available
                </p>
              ) : (
                <ScrollArea className="h-[400px]">
                  <div className="space-y-1">
                    {result.headlines.map((item, i) => (
                      <a
                        key={i}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-zinc-800/60"
                      >
                        <div
                          className={`mt-1.5 size-2 shrink-0 rounded-full ${scoreDot(item.score)}`}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm leading-snug text-zinc-200">
                            {item.headline}
                          </p>
                          <div className="mt-1 flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className="border-zinc-700 text-[10px] text-zinc-500"
                            >
                              {item.source}
                            </Badge>
                            <span className="text-[10px] text-zinc-600">
                              {timeAgo(item.published_at)}
                            </span>
                          </div>
                        </div>
                        <span
                          className={`shrink-0 font-mono text-xs font-medium ${scoreColor(item.score)}`}
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
          <Card className="border-zinc-800 bg-zinc-900">
            <CardHeader>
              <CardTitle className="text-zinc-100">
                Sentiment History —{" "}
                <span className="font-mono text-blue-400">{result.ticker}</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {historyLoading ? (
                <div className="flex h-[250px] items-center justify-center">
                  <Loader2 className="size-6 animate-spin text-zinc-500" />
                </div>
              ) : chartData.length === 0 ? (
                <p className="py-12 text-center text-sm text-zinc-500">
                  No historical data available
                </p>
              ) : (
                <div className="h-[250px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: "#71717a", fontSize: 11 }}
                        axisLine={{ stroke: "#3f3f46" }}
                        tickLine={false}
                      />
                      <YAxis
                        domain={[-1, 1]}
                        ticks={[-1, -0.5, 0, 0.5, 1]}
                        tick={{ fill: "#71717a", fontSize: 11 }}
                        axisLine={{ stroke: "#3f3f46" }}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#18181b",
                          border: "1px solid #3f3f46",
                          borderRadius: "8px",
                          color: "#f4f4f5",
                        }}
                        formatter={(value) => [
                          Number(value).toFixed(3),
                          "Score",
                        ]}
                      />
                      {/* Zero line reference */}
                      <CartesianGrid
                        horizontal={false}
                        vertical={false}
                        strokeDasharray="0"
                        stroke="#3f3f46"
                      />
                      <Line
                        type="monotone"
                        dataKey="score"
                        stroke="#3b82f6"
                        strokeWidth={2}
                        dot={{ fill: "#3b82f6", r: 3 }}
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
