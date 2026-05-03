import { toast } from 'sonner';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

// ── Auth token management ───────────────────────────────────────────────────

const TOKEN_KEY = 'qs_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// ── Pagination ───────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

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
  // Quant-grade extras (added by backend `quant_extras` block; optional for back-compat)
  sortino_ratio?: number;
  calmar_ratio?: number;
  annualized_return_pct?: number;
  max_drawdown_duration_bars?: number;
  downside_deviation?: number;
  deflated_sharpe_ratio?: number;
}

// ── Significance test ─────────────────────────────────────────────
export interface SignificanceRequest {
  ticker: string;
  strategy_type: string;
  params?: Record<string, number>;
  start_date: string;
  end_date: string;
  initial_capital?: number;
}

export interface BootstrapCI {
  point_estimate: number;
  ci_low: number;
  ci_high: number;
  confidence: number;
  n_resamples: number;
}

export interface BlockBootstrapCI extends BootstrapCI {
  avg_block_length: number;
}

export interface PermutationTest {
  observed_sharpe: number;
  p_value: number;
  null_mean: number;
  null_std: number;
  n_permutations: number;
}

export interface SignificanceResponse {
  ticker: string;
  strategy_type: string;
  n_observations: number;
  bootstrap_ci: BootstrapCI;
  block_bootstrap_ci: BlockBootstrapCI;
  permutation: PermutationTest;
  interpretation?: string;
}

// ── Walk-forward (returned from /backtest/optimize) ───────────────
export interface WalkForwardWindow {
  window_id: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  best_params: Record<string, number>;
  is_sharpe: number;
  oos_sharpe: number;
  oos_return_pct: number;
  oos_max_drawdown_pct: number;
  oos_trades: number;
}

export interface WalkForwardResult {
  ticker: string;
  strategy_type: string;
  metric: string;
  n_windows: number;
  train_bars: number;
  test_bars: number;
  oos_sharpe_avg: number;
  oos_sharpe_std: number;
  oos_return_avg_pct: number;
  is_sharpe_avg: number;
  is_vs_oos_degradation_pct: number;
  windows: WalkForwardWindow[];
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

export interface PortfolioHistoryPoint {
  timestamp: string;
  total_value: number;
  cash: number;
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
  stop_loss_pct?: number;
  take_profit_pct?: number;
  atr_stop_multiplier?: number;
}

export interface ParamRange {
  min: number;
  max: number;
  step?: number;
  type: 'int' | 'float' | 'categorical';
  options?: any[];
}

export interface OptimizeRequest {
  ticker: string;
  strategy_type: string;
  start_date: string;
  end_date: string;
  initial_capital?: number;
  param_ranges: Record<string, ParamRange>;
  n_trials?: number;
  metric?: 'sharpe_ratio' | 'total_return_pct' | 'win_rate';
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

// ── Fetch helper ──────────────────────────────────────────────────────────────

interface FetchOptions extends RequestInit {
  timeout?: number;
  retries?: number;
  silent?: boolean;
}

async function fetchJson<T>(
  path: string,
  options: FetchOptions = { timeout: 15000, retries: 2 }
): Promise<T> {
  const { timeout = 15000, retries = 2, silent = false, ...fetchOptions } = options;

  let lastError: Error | null = null;

  for (let i = 0; i <= retries; i++) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);

    try {
      const authHeaders: Record<string, string> = {};
      const token = getToken();
      if (token) authHeaders['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${API_BASE}${path}`, {
        headers: { 'Content-Type': 'application/json', ...authHeaders, ...fetchOptions.headers },
        signal: controller.signal,
        ...fetchOptions,
      });

      clearTimeout(id);

      if (!res.ok) {
        let errorMessage = `API error (${res.status})`;
        try {
          const errorData = await res.json();
          errorMessage = errorData.detail || errorMessage;
        } catch {
          // Fallback to status text
          errorMessage = res.statusText || errorMessage;
        }
        throw new Error(errorMessage);
      }

      if (res.status === 204) return undefined as T;
      return await res.json();
    } catch (err: any) {
      clearTimeout(id);
      lastError = err;

      if (err.name === 'AbortError') {
        lastError = new Error('Request timed out');
      }

      // Retry on network errors or timeouts, but not on business logic errors (4xx)
      // unless it's a 429 or 5xx. For now, simple retry for everything except if we got a status.
      // If lastError has no status, it might be a network error.
      if (i < retries) {
        const delay = Math.pow(2, i) * 1000;
        await new Promise((resolve) => setTimeout(resolve, delay));
        continue;
      }
    }
  }

  if (!silent && lastError) {
    toast.error('API Error', {
      description: lastError.message || 'Failed to communicate with the backend.',
    });
  }

  throw lastError || new Error('Unknown fetch error');
}

// ── API client ────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: number;
  username: string;
}

export const api = {
  health: () => fetchJson<{ status: string }>('/health'),

  auth: {
    register: (username: string, password: string) =>
      fetchJson<{ access_token: string }>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    login: (username: string, password: string) =>
      fetchJson<{ access_token: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    me: () => fetchJson<AuthUser>('/auth/me', { silent: true }),
  },

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
    optimize: (data: OptimizeRequest) =>
      fetchJson<WalkForwardResult>('/backtest/optimize', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    significance: (data: SignificanceRequest) =>
      fetchJson<SignificanceResponse>('/backtest/significance', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    list: (page = 1, pageSize = 20) =>
      fetchJson<PaginatedResponse<BacktestResult>>(`/backtest/results?page=${page}&page_size=${pageSize}`),
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
    history: (ticker: string, page = 1, pageSize = 50) =>
      fetchJson<PaginatedResponse<{ date: string; score: number }>>(
        `/sentiment/history/${encodeURIComponent(ticker)}?page=${page}&page_size=${pageSize}`
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
    history: (page = 1, pageSize = 50) =>
      fetchJson<PaginatedResponse<TradeRecord>>(`/trading/history?page=${page}&page_size=${pageSize}`),
    reset: () => fetchJson<void>('/trading/reset', { method: 'POST' }),
  },

  portfolio: {
    history: (period: string = '1M') =>
      fetchJson<{ points: PortfolioHistoryPoint[] }>(`/portfolio/history?period=${encodeURIComponent(period)}`),
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
