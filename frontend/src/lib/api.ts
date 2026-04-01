const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

// ── Type definitions ──────────────────────────────────────────────────────────

export interface Quote {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  high: number;
  low: number;
}

export interface OHLCVBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ScreenerResult {
  ticker: string;
  price: number;
  rsi: number | null;
  sma_20: number | null;
  sentiment: number | null;
  signal: string;
  score: number;
}

export interface BacktestMetrics {
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  total_trades: number;
  avg_trade_pnl: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
  profit_factor: number;
}

export interface BacktestTrade {
  date: string;
  side: string;
  price: number;
  quantity: number;
  value: number;
  pnl: number;
}

export interface BacktestResult {
  id: number;
  ticker: string;
  strategy_type: string;
  metrics: BacktestMetrics;
  trades: BacktestTrade[];
  equity_curve: [string, number][];
  created_at: string;
}

export interface StrategyInfo {
  name: string;
  description: string;
  default_params: Record<string, number>;
}

export interface SentimentItem {
  headline: string;
  score: number;
  source: string;
  url: string;
  published_at: string;
}

export interface SentimentResult {
  ticker: string;
  overall_score: number;
  vader_avg: number;
  llm_score: number | null;
  trend: string;
  num_sources: number;
  headlines: SentimentItem[];
  updated_at: string;
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  market_value: number;
}

export interface Portfolio {
  total_value: number;
  cash: number;
  positions_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  positions: Position[];
  daily_pnl: number;
}

export interface TradeRecord {
  id: string;
  ticker: string;
  side: string;
  order_type: string;
  price: number;
  quantity: number;
  value: number;
  timestamp: string;
}

export interface WatchlistItem {
  ticker: string;
  name: string;
}

export interface SearchResult {
  ticker: string;
  name: string;
  exchange: string;
}

export interface OrderRequest {
  ticker: string;
  side: 'buy' | 'sell';
  order_type: 'market' | 'limit';
  quantity: number;
  limit_price?: number;
}

export interface BacktestRequest {
  ticker: string;
  strategy_type: string;
  start_date: string;
  end_date: string;
  initial_capital?: number;
  params?: Record<string, number>;
}

export interface AutoTradeDecision {
  ticker: string;
  action: string;
  quantity: number;
  price: number;
  confidence: number;
  reasons: string[];
}

export interface AutoTradeExecution {
  ticker: string;
  action: string;
  status: string;
  filled_price?: number;
  quantity?: number;
  confidence?: number;
  reasons: string[];
}

export interface AutoTradeResult {
  timestamp: string;
  decisions: AutoTradeDecision[];
  executions: AutoTradeExecution[];
  portfolio: {
    total_value: number;
    cash: number;
    positions_count: number;
    total_pnl: number;
    total_pnl_pct: number;
  };
}

export interface CompareResult {
  strategy_name: string;
  strategy_type: string;
  winner: boolean;
  metrics: {
    total_return_pct: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    win_rate: number;
    total_trades: number;
    profit_factor: number;
    final_value: number;
  };
}

export interface CompareResponse {
  ticker: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  results: CompareResult[];
}

export interface ChartIndicators {
  sma_20: (number | null)[];
  rsi: (number | null)[];
  bollinger_upper: (number | null)[];
  bollinger_lower: (number | null)[];
}

export interface AutoTradeAnalysis {
  analyses: {
    ticker: string;
    price?: number;
    sentiment_score?: number;
    rsi?: number | null;
    sma_20?: number | null;
    signal: string;
    confidence: number;
    reasons: string[];
  }[];
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || 'API error');
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── API client ────────────────────────────────────────────────────────────────

export const api = {
  health: () => fetchJson<{ status: string }>('/health'),

  market: {
    search: (q: string) =>
      fetchJson<{ results: SearchResult[] }>(`/market/search?q=${encodeURIComponent(q)}`),
    quote: (ticker: string) =>
      fetchJson<Quote>(`/market/quote/${encodeURIComponent(ticker)}`),
    ohlcv: (ticker: string, start: string, end: string) =>
      fetchJson<OHLCVBar[]>(
        `/market/ohlcv/${encodeURIComponent(ticker)}?start=${start}&end=${end}`
      ),
    screener: () => fetchJson<ScreenerResult[]>('/market/screener'),
  },

  backtest: {
    run: (data: BacktestRequest) =>
      fetchJson<BacktestResult>('/backtest/run', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    list: () => fetchJson<BacktestResult[]>('/backtest/results'),
    get: (id: number) => fetchJson<BacktestResult>(`/backtest/results/${id}`),
    strategies: () => fetchJson<StrategyInfo[]>('/backtest/strategies'),
    delete: (id: number) =>
      fetchJson<void>(`/backtest/results/${id}`, { method: 'DELETE' }),
    compare: (ticker: string, startDate: string, endDate: string, capital?: number) =>
      fetchJson<CompareResponse>(`/backtest/compare?ticker=${ticker}&start_date=${startDate}&end_date=${endDate}&initial_capital=${capital || 100000}`, { method: 'POST' }),
    exportCsv: (id: number) => `${API_BASE}/backtest/results/${id}/export?format=csv`,
  },

  sentiment: {
    analyze: (ticker: string) =>
      fetchJson<SentimentResult>(`/sentiment/analyze/${encodeURIComponent(ticker)}`),
    feed: () => fetchJson<SentimentResult[]>('/sentiment/feed'),
    history: (ticker: string) =>
      fetchJson<{ date: string; score: number }[]>(
        `/sentiment/history/${encodeURIComponent(ticker)}`
      ),
  },

  trading: {
    order: (data: OrderRequest) =>
      fetchJson<TradeRecord>('/trading/order', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    positions: () => fetchJson<Position[]>('/trading/positions'),
    portfolio: () => fetchJson<Portfolio>('/trading/portfolio'),
    history: () => fetchJson<TradeRecord[]>('/trading/history'),
    reset: () => fetchJson<void>('/trading/reset', { method: 'POST' }),
  },

  settings: {
    watchlist: () => fetchJson<WatchlistItem[]>('/settings/watchlist'),
    addToWatchlist: (ticker: string, name?: string) =>
      fetchJson<void>('/settings/watchlist', {
        method: 'POST',
        body: JSON.stringify({ ticker, name }),
      }),
    removeFromWatchlist: (ticker: string) =>
      fetchJson<void>(`/settings/watchlist/${encodeURIComponent(ticker)}`, {
        method: 'DELETE',
      }),
    getConfig: () => fetchJson<Record<string, string>>('/settings/config'),
    updateConfig: (data: Record<string, string>) =>
      fetchJson<void>('/settings/config', {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
  },

  autoTrade: {
    run: () => fetchJson<AutoTradeResult>('/auto-trade/run', { method: 'POST' }),
    analyze: () => fetchJson<AutoTradeAnalysis>('/auto-trade/analyze', { method: 'POST' }),
  },
};

// ── WebSocket helper ──────────────────────────────────────────────────────────

const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL ||
  API_BASE.replace(/^http/, 'ws').replace(/\/api$/, '/api');

export function createWebSocket(
  onMessage: (data: unknown) => void,
  onError?: (err: Event) => void
): WebSocket {
  const ws = new WebSocket(`${WS_BASE}/ws/live`);
  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      onMessage(event.data);
    }
  };
  if (onError) ws.onerror = onError;
  return ws;
}
