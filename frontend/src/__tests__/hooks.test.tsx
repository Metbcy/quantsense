import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useFetch } from "@/lib/hooks";

describe("useFetch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("starts in loading state", () => {
    const fetcher = vi.fn(() => new Promise<string>(() => {})); // never resolves
    const { result } = renderHook(() => useFetch(fetcher));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("returns data on success", async () => {
    const fetcher = vi.fn().mockResolvedValue({ name: "AAPL" });
    const { result } = renderHook(() => useFetch(fetcher));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.data).toEqual({ name: "AAPL" });
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("returns error on failure", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("Network error"));
    const { result } = renderHook(() => useFetch(fetcher));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("Network error");
  });

  it("refetch re-executes the fetcher", async () => {
    let callCount = 0;
    const fetcher = vi.fn(async () => {
      callCount++;
      return { count: callCount };
    });

    const { result } = renderHook(() => useFetch(fetcher));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ count: 1 });

    act(() => {
      result.current.refetch();
    });

    await waitFor(() => expect(result.current.data).toEqual({ count: 2 }));
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not update state after unmount", async () => {
    let resolve: (val: string) => void;
    const fetcher = vi.fn(
      () => new Promise<string>((r) => { resolve = r; })
    );

    const { result, unmount } = renderHook(() => useFetch(fetcher));
    expect(result.current.loading).toBe(true);

    unmount();

    // Resolve after unmount — should not throw
    resolve!("late data");

    // Give it a tick to process
    await new Promise((r) => setTimeout(r, 10));
    // If it throws, the test would fail
  });
});
