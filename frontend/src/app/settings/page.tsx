"use client";

import { useState, useEffect, useCallback } from "react";
import {
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
import { PageHeader } from "@/components/page-header";
import { useWatchlist } from "@/lib/hooks";
import { api } from "@/lib/api";
import { SettingsSkeleton } from "@/components/loading";

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
  const [refreshInterval, setRefreshInterval] = useState(30);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [webhookSecret, setWebhookSecret] = useState("");
  const [resetting, setResetting] = useState(false);

  // Password visibility
  const [showGroq, setShowGroq] = useState(false);
  const [showOpenai, setShowOpenai] = useState(false);
  const [showWebhook, setShowWebhook] = useState(false);

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const cfg = await api.settings.getConfig();
      setInitialCash(cfg.initial_cash || "100000");
      setGroqKey(cfg.groq_api_key || "");
      setOpenaiKey(cfg.openai_api_key || "");
      setWebhookSecret(cfg.webhook_secret || "");
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
        webhook_secret: webhookSecret,
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

  if (configLoading) return <SettingsSkeleton />;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        eyebrow="System"
        title="Settings"
        description="Manage your watchlist, paper-trading defaults, API credentials, and webhooks."
        actions={
          <Button onClick={handleSaveConfig} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-1.5 size-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 size-4" />
            )}
            Save changes
          </Button>
        }
      />

      {/* Watchlist Management */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle>Watchlist</CardTitle>
          <CardDescription>Manage your tracked tickers.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Current watchlist */}
          <div className="flex flex-wrap gap-1.5">
            {watchlistLoading ? (
              <div className="h-5 w-32 animate-pulse rounded-sm bg-muted" />
            ) : watchlist.length === 0 ? (
              <p className="text-sm text-muted-foreground">No tickers in watchlist</p>
            ) : (
              watchlist.map((item) => (
                <Badge
                  key={item.ticker}
                  variant="secondary"
                  className="gap-1 px-1.5 py-0.5"
                >
                  <span className="font-mono">{item.ticker}</span>
                  {item.name && (
                    <span className="font-normal normal-case tracking-normal text-muted-foreground">
                      · {item.name}
                    </span>
                  )}
                  <button
                    onClick={() => handleRemoveTicker(item.ticker)}
                    className="ml-0.5 rounded-sm p-0.5 transition-colors duration-150 hover:bg-accent"
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
              className="font-mono"
            />
            <Button
              onClick={handleAddTicker}
              disabled={addingTicker || !newTicker.trim()}
              className="shrink-0"
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
      <Card>
        <CardHeader className="border-b">
          <CardTitle>Paper trading</CardTitle>
          <CardDescription>Configure simulated trading parameters.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="initial-cash">Initial cash ($)</Label>
            <Input
              id="initial-cash"
              type="number"
              value={initialCash}
              onChange={(e) => setInitialCash(e.target.value)}
              className="font-mono"
            />
          </div>

          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline" className="text-loss hover:text-loss">
                <RotateCcw className="mr-1.5 size-4" />
                Reset portfolio
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Reset portfolio?</DialogTitle>
                <DialogDescription>
                  This will clear all positions, trade history, and reset your cash
                  balance. This action cannot be undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button
                  onClick={handleReset}
                  disabled={resetting}
                  variant="destructive"
                >
                  {resetting && <Loader2 className="mr-1.5 size-4 animate-spin" />}
                  Confirm reset
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-1.5">
            <Key className="size-3.5 text-muted-foreground" strokeWidth={1.75} />
            API keys
          </CardTitle>
          <CardDescription>
            Configure LLM provider credentials for sentiment analysis.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {[
            {
              id: "groq",
              label: "Groq API key",
              value: groqKey,
              set: setGroqKey,
              show: showGroq,
              toggle: () => setShowGroq(!showGroq),
            },
            {
              id: "openai",
              label: "OpenAI API key",
              value: openaiKey,
              set: setOpenaiKey,
              show: showOpenai,
              toggle: () => setShowOpenai(!showOpenai),
            },
          ].map((field) => (
            <div key={field.id} className="space-y-1.5">
              <Label htmlFor={field.id}>{field.label}</Label>
              <div className="relative">
                <Input
                  id={field.id}
                  type={field.show ? "text" : "password"}
                  value={field.value}
                  onChange={(e) => field.set(e.target.value)}
                  placeholder="sk-..."
                  className="pr-9 font-mono"
                />
                <button
                  type="button"
                  onClick={field.toggle}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors duration-150 hover:text-foreground"
                >
                  {field.show ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                </button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Sentiment Settings */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle>Sentiment</CardTitle>
          <CardDescription>Configure automated sentiment analysis.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <Label>Refresh interval</Label>
              <span className="font-mono text-xs tabular-nums text-foreground">
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
            <div className="flex justify-between font-mono text-[10px] text-muted-foreground">
              <span>5 min</span>
              <span>120 min</span>
            </div>
          </div>

          <Separator />

          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-0.5">
              <Label className="normal-case tracking-normal text-foreground" style={{ fontSize: 13, letterSpacing: 0 }}>
                Auto-refresh
              </Label>
              <p className="text-xs text-muted-foreground">
                Automatically refresh sentiment data at the interval above.
              </p>
            </div>
            <Switch checked={autoRefresh} onCheckedChange={setAutoRefresh} />
          </div>
        </CardContent>
      </Card>

      {/* TradingView Webhook */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle>TradingView webhook</CardTitle>
          <CardDescription>Execute trades directly from TradingView alerts.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1.5">
            <Label>Webhook URL</Label>
            <div className="rounded-md border border-border bg-muted/40 px-2.5 py-2 font-mono text-[11px] text-primary">
              {typeof window !== "undefined"
                ? `${window.location.origin}/api/webhooks/tradingview`
                : "/api/webhooks/tradingview"}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="webhook-secret">Webhook secret</Label>
            <div className="relative">
              <Input
                id="webhook-secret"
                type={showWebhook ? "text" : "password"}
                value={webhookSecret}
                onChange={(e) => setWebhookSecret(e.target.value)}
                placeholder="Enter a secure secret"
                className="pr-9 font-mono"
              />
              <button
                type="button"
                onClick={() => setShowWebhook(!showWebhook)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors duration-150 hover:text-foreground"
              >
                {showWebhook ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              </button>
            </div>
          </div>

          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="mb-2 text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">
              Message template (JSON)
            </p>
            <pre className="overflow-x-auto font-mono text-[11px] leading-relaxed text-foreground">
{`{
  "secret": "${webhookSecret ? "••••••••" : "YOUR_SECRET"}",
  "ticker": "{{ticker}}",
  "action": "buy",
  "quantity": 10
}`}
            </pre>
          </div>
        </CardContent>
      </Card>

      {/* Bottom save */}
      <div className="flex justify-end pb-2">
        <Button onClick={handleSaveConfig} disabled={saving}>
          {saving ? (
            <Loader2 className="mr-1.5 size-4 animate-spin" />
          ) : (
            <Save className="mr-1.5 size-4" />
          )}
          Save all settings
        </Button>
      </div>
    </div>
  );
}
