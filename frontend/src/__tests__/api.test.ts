import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { getToken, setToken, clearToken } from "@/lib/api";

const TOKEN_KEY = "qs_token";

describe("Token management", () => {
  beforeEach(() => {
    localStorage.removeItem(TOKEN_KEY);
  });

  it("returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });

  it("stores and retrieves a token", () => {
    setToken("test-jwt-123");
    expect(getToken()).toBe("test-jwt-123");
  });

  it("clears the token", () => {
    setToken("test-jwt-123");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("overwrites an existing token", () => {
    setToken("old-token");
    setToken("new-token");
    expect(getToken()).toBe("new-token");
  });
});

describe("API client structure", () => {
  it("exports an api object with expected namespaces", async () => {
    const { api } = await import("@/lib/api");
    expect(api).toBeDefined();
    expect(api.health).toBeTypeOf("function");
    expect(api.auth).toBeDefined();
    expect(api.auth.register).toBeTypeOf("function");
    expect(api.auth.login).toBeTypeOf("function");
    expect(api.auth.me).toBeTypeOf("function");
    expect(api.market).toBeDefined();
    expect(api.market.quote).toBeTypeOf("function");
    expect(api.market.ohlcv).toBeTypeOf("function");
    expect(api.market.search).toBeTypeOf("function");
    expect(api.backtest).toBeDefined();
    expect(api.backtest.run).toBeTypeOf("function");
    expect(api.backtest.list).toBeTypeOf("function");
    expect(api.sentiment).toBeDefined();
    expect(api.sentiment.analyze).toBeTypeOf("function");
    expect(api.trading).toBeDefined();
    expect(api.trading.order).toBeTypeOf("function");
    expect(api.trading.portfolio).toBeTypeOf("function");
    expect(api.settings).toBeDefined();
    expect(api.settings.watchlist).toBeTypeOf("function");
    expect(api.autoTrade).toBeDefined();
    expect(api.autoTrade.run).toBeTypeOf("function");
  });
});

describe("fetchJson behavior", () => {
  beforeEach(() => {
    localStorage.removeItem(TOKEN_KEY);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("includes Authorization header when token is set", async () => {
    setToken("my-jwt");

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "ok" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("@/lib/api");
    await api.health();

    expect(mockFetch).toHaveBeenCalled();
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Authorization"]).toBe("Bearer my-jwt");
  });

  it("does not include Authorization header when no token", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: "ok" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("@/lib/api");
    await api.health();

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Authorization"]).toBeUndefined();
  });

  it("throws on non-ok response", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ detail: "Resource not found" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { api } = await import("@/lib/api");
    await expect(api.health()).rejects.toThrow("Resource not found");
  });
});
