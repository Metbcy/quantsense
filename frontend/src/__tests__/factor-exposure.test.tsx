import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FactorExposurePanel } from "@/components/factor-exposure";
import type { FactorExposureResult } from "@/lib/api";

const sample: FactorExposureResult = {
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

describe("<FactorExposurePanel />", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("qs_token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the trigger and computes factor exposure on click", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(sample),
    });
    vi.stubGlobal("fetch", mockFetch);

    render(<FactorExposurePanel resultId={7} />);

    // Trigger button is present pre-click.
    const trigger = screen.getByRole("button", {
      name: /compute factor exposure/i,
    });
    expect(trigger).toBeInTheDocument();

    // Default model is FF3; the radio group exposes the three options.
    expect(screen.getByRole("radio", { name: /ff3/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    fireEvent.click(trigger);

    // Wait for the alpha row to appear.
    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeInTheDocument();
    });

    // Annualized alpha (formatted with sign + .toFixed(2)) appears in the
    // table cell for the Alpha row.
    expect(screen.getAllByText("+4.20%").length).toBeGreaterThanOrEqual(1);

    // At least one factor row renders — Mkt-RF coefficient.
    expect(screen.getByText("Mkt-RF")).toBeInTheDocument();
    expect(screen.getByText("0.950")).toBeInTheDocument();

    // R² values display.
    expect(screen.getByText("0.840")).toBeInTheDocument();
    expect(screen.getByText("0.835")).toBeInTheDocument();

    // The interpretation line marks alpha as significant at the 5% level
    // (alpha_pvalue = 0.0012 < 0.05).
    expect(
      screen.getByText(/significant at the 5% level/i),
    ).toBeInTheDocument();

    // Verify the request body sent to the backend.
    const [url, options] = mockFetch.mock.calls[0];
    expect(url).toContain("/backtest/factor-exposure");
    const body = JSON.parse(options.body as string);
    expect(body).toEqual({ result_id: 7, model: "ff3" });
  });

  it("switches model via the segmented control before computing", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ ...sample, model: "ff5" }),
    });
    vi.stubGlobal("fetch", mockFetch);

    render(<FactorExposurePanel resultId={11} />);

    fireEvent.click(screen.getByRole("radio", { name: /ff5/i }));
    expect(screen.getByRole("radio", { name: /ff5/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    fireEvent.click(
      screen.getByRole("button", { name: /compute factor exposure/i }),
    );

    await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body as string);
    expect(body).toEqual({ result_id: 11, model: "ff5" });
  });
});
