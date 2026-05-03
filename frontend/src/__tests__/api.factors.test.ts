import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { FactorExposureResult } from "@/lib/api";

// Shape-faithful to FactorExposure.to_dict() in backend/engine/factors.py.
const sampleFactorResponse: FactorExposureResult = {
  model: "ff3",
  alpha: 4.2,
  alpha_se: 1.3,
  alpha_t: 3.23,
  alpha_pvalue: 0.0012,
  factors: {
    "Mkt-RF": { coefficient: 0.95, se: 0.05, t_stat: 19.0, pvalue: 0.0 },
    SMB: { coefficient: 0.12, se: 0.08, t_stat: 1.5, pvalue: 0.13 },
    HML: { coefficient: -0.04, se: 0.07, t_stat: -0.57, pvalue: 0.57 },
  },
  r_squared: 0.84,
  adj_r_squared: 0.835,
  n_obs: 252,
  start_date: "2020-01-02",
  end_date: "2020-12-31",
  risk_free_subtracted: true,
};

describe("computeFactorExposure", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("qs_token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs to /api/backtest/factor-exposure with model + result_id", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(sampleFactorResponse),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { computeFactorExposure } = await import("@/lib/api");

    const result = await computeFactorExposure({
      result_id: 42,
      model: "ff3",
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/backtest/factor-exposure");
    expect(options.method).toBe("POST");

    const body = JSON.parse(options.body as string);
    expect(body).toEqual({ result_id: 42, model: "ff3" });

    expect(result.model).toBe("ff3");
    expect(result.alpha).toBeCloseTo(4.2);
    expect(result.alpha_pvalue).toBeLessThan(0.05);
    expect(Object.keys(result.factors)).toEqual(["Mkt-RF", "SMB", "HML"]);
    expect(result.factors["Mkt-RF"].coefficient).toBeCloseTo(0.95);
    expect(result.r_squared).toBeCloseTo(0.84);
    expect(result.n_obs).toBe(252);
  });

  it("supports the explicit returns/dates path with carhart4 model", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          ...sampleFactorResponse,
          model: "carhart4",
          factors: {
            "Mkt-RF": { coefficient: 0.95, se: 0.05, t_stat: 19, pvalue: 0 },
            SMB: { coefficient: 0.12, se: 0.08, t_stat: 1.5, pvalue: 0.13 },
            HML: { coefficient: -0.04, se: 0.07, t_stat: -0.57, pvalue: 0.57 },
            Mom: { coefficient: 0.07, se: 0.04, t_stat: 1.75, pvalue: 0.08 },
          },
        }),
    });
    vi.stubGlobal("fetch", mockFetch);

    const { computeFactorExposure } = await import("@/lib/api");

    const result = await computeFactorExposure({
      returns: [0.001, -0.002, 0.003],
      dates: ["2020-01-02", "2020-01-03", "2020-01-06"],
      model: "carhart4",
      risk_free_subtract: true,
    });

    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body as string);
    expect(body.model).toBe("carhart4");
    expect(body.returns).toEqual([0.001, -0.002, 0.003]);
    expect(body.dates).toEqual(["2020-01-02", "2020-01-03", "2020-01-06"]);
    expect(body.risk_free_subtract).toBe(true);

    expect(result.model).toBe("carhart4");
    expect(Object.keys(result.factors)).toContain("Mom");
  });
});
