"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Settings as SettingsIcon,
  X,
  Plus,
  Loader2,
  RotateCcw,
  Key,
  Eye,
  EyeOff,
  Save,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogClose,
} from "@/components/ui/dialog";
import { useWatchlist } from "@/lib/hooks";
import { api } from "@/lib/api";
import { Loading } from "@/components/loading";

export default function SettingsPage() {
  const { watchlist, loading: watchlistLoading, add, remove } = useWatchlist();

  const [newTicker, setNewTicker] = useState("");
  const [addingTicker, setAddingTicker] = useState(false);

  // Config state
  const [configLoading, setConfigLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [initialCash, setInitialCash] = useState("100000");
  const [groqKey, setGroqKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [refreshInterval, setRefreshInterval] = useState(30);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [resetting, setResetting] = useState(false);

  // Password visibility
  const [showGroq, setShowGroq] = useState(false);
  const [showOpenai, setShowOpenai] = useState(false);
  const [showAnthropic, setShowAnthropic] = useState(false);

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const cfg = await api.settings.getConfig();
      setInitialCash(cfg.initial_cash || "100000");
      setGroqKey(cfg.groq_api_key || "");
      setOpenaiKey(cfg.openai_api_key || "");
      setAnthropicKey(cfg.anthropic_api_key || "");
      setRefreshInterval(parseInt(cfg.sentiment_refresh_interval || "30", 10));
      setAutoRefresh(cfg.sentiment_auto_refresh === "true");
    } catch {
      // Config may not exist yet
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  async function handleAddTicker() {
    const t = newTicker.trim().toUpperCase();
    if (!t) return;
    setAddingTicker(true);
    try {
      await add(t);
      setNewTicker("");
      toast.success(`${t} added to watchlist`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add ticker");
    } finally {
      setAddingTicker(false);
    }
  }

  async function handleRemoveTicker(ticker: string) {
    try {
      await remove(ticker);
      toast.success(`${ticker} removed from watchlist`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to remove");
    }
  }

  async function handleSaveConfig() {
    setSaving(true);
    try {
      await api.settings.updateConfig({
        initial_cash: initialCash,
        groq_api_key: groqKey,
        openai_api_key: openaiKey,
        anthropic_api_key: anthropicKey,
        sentiment_refresh_interval: refreshInterval.toString(),
        sentiment_auto_refresh: autoRefresh.toString(),
      });
      toast.success("Settings saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  async function handleReset() {
    setResetting(true);
    try {
      await api.trading.reset();
      toast.success("Portfolio reset to initial state");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setResetting(false);
    }
  }

  if (configLoading) return <Loading />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <SettingsIcon className="size-6 text-blue-500" />
        <h1 className="text-2xl font-bold text-zinc-100">Settings</h1>
      </div>

      {/* Watchlist Management */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="text-zinc-100">Watchlist</CardTitle>
          <CardDescription className="text-zinc-500">
            Manage your tracked tickers
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Current watchlist */}
          <div className="flex flex-wrap gap-2">
            {watchlistLoading ? (
              <div className="h-5 w-32 animate-pulse rounded bg-zinc-800" />
            ) : watchlist.length === 0 ? (
              <p className="text-sm text-zinc-500">No tickers in watchlist</p>
            ) : (
              watchlist.map((item) => (
                <Badge
                  key={item.ticker}
                  variant="secondary"
                  className="gap-1 bg-zinc-800 px-2.5 py-1 text-zinc-200"
                >
                  <span className="font-mono">{item.ticker}</span>
                  {item.name && (
                    <span className="text-zinc-500">· {item.name}</span>
                  )}
                  <button
                    onClick={() => handleRemoveTicker(item.ticker)}
                    className="ml-1 rounded-full p-0.5 hover:bg-zinc-700"
                  >
                    <X className="size-3" />
                  </button>
                </Badge>
              ))
            )}
          </div>

          {/* Add ticker */}
          <div className="flex gap-2">
            <Input
              value={newTicker}
              onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && handleAddTicker()}
              placeholder="Add ticker (e.g. TSLA)"
              className="border-zinc-700 bg-zinc-950 font-mono text-zinc-100 placeholder:text-zinc-600"
            />
            <Button
              onClick={handleAddTicker}
              disabled={addingTicker || !newTicker.trim()}
              className="shrink-0 bg-blue-600 text-white hover:bg-blue-700"
            >
              {addingTicker ? (
                <Loader2 className="mr-1 size-4 animate-spin" />
              ) : (
                <Plus className="mr-1 size-4" />
              )}
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Paper Trading */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="text-zinc-100">Paper Trading</CardTitle>
          <CardDescription className="text-zinc-500">
            Configure simulated trading parameters
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label className="text-zinc-400">Initial Cash ($)</Label>
            <Input
              type="number"
              value={initialCash}
              onChange={(e) => setInitialCash(e.target.value)}
              className="border-zinc-700 bg-zinc-950 text-zinc-100"
            />
          </div>

          <Dialog>
            <DialogTrigger asChild>
              <Button
                variant="destructive"
                className="bg-red-500/10 text-red-400 hover:bg-red-500/20"
              >
                <RotateCcw className="mr-2 size-4" />
                Reset Portfolio
              </Button>
            </DialogTrigger>
            <DialogContent className="border-zinc-700 bg-zinc-900">
              <DialogHeader>
                <DialogTitle className="text-zinc-100">Reset Portfolio?</DialogTitle>
                <DialogDescription className="text-zinc-400">
                  This will clear all positions, trade history, and reset your
                  cash balance. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline" className="border-zinc-700 text-zinc-300">
                    Cancel
                  </Button>
                </DialogClose>
                <Button
                  onClick={handleReset}
                  disabled={resetting}
                  className="bg-red-600 text-white hover:bg-red-700"
                >
                  {resetting && <Loader2 className="mr-2 size-4 animate-spin" />}
                  Confirm Reset
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-zinc-100">
            <Key className="size-4" />
            API Keys
          </CardTitle>
          <CardDescription className="text-zinc-500">
            Configure LLM provider credentials for sentiment analysis
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {[
            {
              label: "Groq API Key",
              value: groqKey,
              set: setGroqKey,
              show: showGroq,
              toggle: () => setShowGroq(!showGroq),
            },
            {
              label: "OpenAI API Key",
              value: openaiKey,
              set: setOpenaiKey,
              show: showOpenai,
              toggle: () => setShowOpenai(!showOpenai),
            },
            {
              label: "Anthropic API Key",
              value: anthropicKey,
              set: setAnthropicKey,
              show: showAnthropic,
              toggle: () => setShowAnthropic(!showAnthropic),
            },
          ].map((field) => (
            <div key={field.label} className="space-y-1">
              <Label className="text-zinc-400">{field.label}</Label>
              <div className="relative">
                <Input
                  type={field.show ? "text" : "password"}
                  value={field.value}
                  onChange={(e) => field.set(e.target.value)}
                  placeholder="sk-..."
                  className="border-zinc-700 bg-zinc-950 pr-10 font-mono text-zinc-100 placeholder:text-zinc-600"
                />
                <button
                  type="button"
                  onClick={field.toggle}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                >
                  {field.show ? (
                    <EyeOff className="size-4" />
                  ) : (
                    <Eye className="size-4" />
                  )}
                </button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Sentiment Settings */}
      <Card className="border-zinc-800 bg-zinc-900">
        <CardHeader>
          <CardTitle className="text-zinc-100">Sentiment Settings</CardTitle>
          <CardDescription className="text-zinc-500">
            Configure automated sentiment analysis
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-zinc-400">Refresh Interval</Label>
              <span className="font-mono text-sm text-zinc-300">
                {refreshInterval} min
              </span>
            </div>
            <Slider
              value={[refreshInterval]}
              onValueChange={(value) => {
                const v = Array.isArray(value) ? value[0] : value;
                setRefreshInterval(v);
              }}
              min={5}
              max={120}
            />
            <div className="flex justify-between text-[10px] text-zinc-600">
              <span>5 min</span>
              <span>120 min</span>
            </div>
          </div>

          <Separator className="bg-zinc-800" />

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-zinc-300">Auto-refresh</Label>
              <p className="text-xs text-zinc-500">
                Automatically refresh sentiment data at the interval above
              </p>
            </div>
            <Switch
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end pb-6">
        <Button
          onClick={handleSaveConfig}
          disabled={saving}
          className="bg-blue-600 px-8 text-white hover:bg-blue-700"
        >
          {saving ? (
            <Loader2 className="mr-2 size-4 animate-spin" />
          ) : (
            <Save className="mr-2 size-4" />
          )}
          Save All Settings
        </Button>
      </div>
    </div>
  );
}
