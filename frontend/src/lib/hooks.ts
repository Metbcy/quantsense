"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { api, createWebSocket } from "@/lib/api";
import type { Portfolio, WatchlistItem } from "@/lib/api";

// ── Generic data-fetching hook ────────────────────────────────────────────────

interface UseFetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useFetch<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = []
): UseFetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const refetch = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher()
      .then((result) => {
        if (mountedRef.current) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (mountedRef.current) {
          setError(err.message);
          setLoading(false);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mountedRef.current = true;
    refetch();
    return () => {
      mountedRef.current = false;
    };
  }, [refetch]);

  return { data, loading, error, refetch };
}

// ── Portfolio hook (auto-refreshes every 30s) ─────────────────────────────────

export function usePortfolio() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetch = useCallback(() => {
    api.trading
      .portfolio()
      .then((data) => {
        if (mountedRef.current) {
          setPortfolio(data);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (mountedRef.current) {
          setError(err.message);
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetch();
    const interval = setInterval(fetch, 30_000);
    return () => {
      mountedRef.current = false;
      clearInterval(interval);
    };
  }, [fetch]);

  return { portfolio, loading, error, refetch: fetch };
}

// ── Watchlist hook with add/remove ────────────────────────────────────────────

export function useWatchlist() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const fetchWatchlist = useCallback(() => {
    setLoading(true);
    api.settings
      .watchlist()
      .then((data) => {
        if (mountedRef.current) {
          setWatchlist(data);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (mountedRef.current) {
          setError(err.message);
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    fetchWatchlist();
    return () => {
      mountedRef.current = false;
    };
  }, [fetchWatchlist]);

  const add = useCallback(
    async (ticker: string, name?: string) => {
      await api.settings.addToWatchlist(ticker, name);
      fetchWatchlist();
    },
    [fetchWatchlist]
  );

  const remove = useCallback(
    async (ticker: string) => {
      await api.settings.removeFromWatchlist(ticker);
      fetchWatchlist();
    },
    [fetchWatchlist]
  );

  return { watchlist, loading, error, add, remove, refetch: fetchWatchlist };
}

// ── WebSocket hook with auto-reconnect ────────────────────────────────────────

export function useWebSocket(onMessage: (data: unknown) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    let unmounted = false;

    function connect() {
      if (unmounted) return;

      const ws = createWebSocket(
        (data) => onMessageRef.current(data),
        () => scheduleReconnect()
      );

      ws.onclose = () => {
        if (!unmounted) scheduleReconnect();
      };

      wsRef.current = ws;
    }

    function scheduleReconnect() {
      if (unmounted) return;
      reconnectTimer.current = setTimeout(connect, 3000);
    }

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
      }
    };
  }, []);

  return wsRef;
}
