"use client";

import { useState } from "react";
import { Sigma } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import type { FactorExposureResult, FactorModel } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODELS: { value: FactorModel; label: string; factors: string }[] = [
  { value: "ff3", label: "FF3", factors: "Mkt-RF, SMB, HML" },
  { value: "ff5", label: "FF5", factors: "Mkt-RF, SMB, HML, RMW, CMA" },
  { value: "carhart4", label: "Carhart-4", factors: "Mkt-RF, SMB, HML, Mom" },
];

function formatPct(n: number) {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function formatCoef(n: number) {
  return n.toFixed(3);
}

function formatP(n: number) {
  return n < 0.001 ? "<0.001" : n.toFixed(3);
}

export interface FactorExposurePanelProps {
  /** Saved backtest result id. The component will not render its CTA until provided. */
  resultId: number;
  /** Optional className to merge with the outer wrapper. */
  className?: string;
}

/**
 * FactorExposurePanel — embedded at the bottom of the backtest results card.
 *
 * Lets the user pick FF3 / FF5 / Carhart-4 and decompose their saved
 * backtest's daily returns onto Fama-French factors. Renders alpha,
 * per-factor coefficient/t-stat/p-value, R², adj-R², and a one-line
 * interpretation.
 *
 * The panel never fires automatically — only on explicit button click —
 * because the regression is non-trivial and the user may not want it
 * for every backtest.
 */
export function FactorExposurePanel({ resultId, className }: FactorExposurePanelProps) {
  const [model, setModel] = useState<FactorModel>("ff3");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<FactorExposureResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Drop the cached result when the user switches to a new backtest run.
  // We key the panel on `resultId` from the parent, so re-rendering with a
  // new id resets state via the natural prop-change cycle below.
  const [lastResultId, setLastResultId] = useState(resultId);
  if (lastResultId !== resultId) {
    setLastResultId(resultId);
    setResult(null);
    setError(null);
  }

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      const res = await api.backtest.factorExposure({
        result_id: resultId,
        model,
      });
      setResult(res);
      toast.success("Factor exposure computed");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Factor exposure failed";
      setError(msg);
      toast.error(msg);
    } finally {
      setRunning(false);
    }
  }

  const factorNames = result ? Object.keys(result.factors) : [];
  const alphaSignificant = result ? result.alpha_pvalue < 0.05 : false;

  return (
    <div
      className={cn(
        "mt-4 rounded-md border border-border bg-muted/20 p-4",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
            <Sigma className="size-4 text-muted-foreground" strokeWidth={1.75} />
            Factor exposure
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Decompose returns onto Fama-French factors. Alpha is the
            intercept after controlling for the chosen risk premia —
            closer to evidence of edge than raw Sharpe.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {/* Segmented model picker — button row, ochre-tinted active state */}
          <div
            role="radiogroup"
            aria-label="Factor model"
            className="inline-flex items-center gap-0.5 rounded-md border border-border bg-card p-0.5"
          >
            {MODELS.map((m) => {
              const active = m.value === model;
              return (
                <button
                  key={m.value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setModel(m.value)}
                  className={cn(
                    "rounded-sm px-2.5 py-1 text-[11px] font-mono uppercase tracking-wider transition-colors duration-150",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                  )}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRun}
            disabled={running}
          >
            {running ? "Computing…" : "Compute factor exposure"}
          </Button>
        </div>
      </div>

      {error && !running && (
        <p className="mt-3 text-xs text-loss">{error}</p>
      )}

      {result && (
        <div className="mt-4 space-y-3">
          <div className="overflow-hidden rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Term</TableHead>
                  <TableHead className="text-right">Coefficient</TableHead>
                  <TableHead className="text-right">t-stat</TableHead>
                  <TableHead className="pr-4 text-right">p-value</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="pl-4">
                    <span className="font-medium text-foreground">Alpha</span>
                    <span className="ml-2 font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
                      annualized
                    </span>
                  </TableCell>
                  <TableCell
                    className={cn(
                      "text-right font-mono tabular-nums",
                      alphaSignificant && result.alpha >= 0 && "text-profit",
                      alphaSignificant && result.alpha < 0 && "text-loss",
                    )}
                  >
                    {formatPct(result.alpha)}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {result.alpha_t.toFixed(2)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      "pr-4 text-right font-mono tabular-nums",
                      alphaSignificant ? "text-primary" : "text-muted-foreground",
                    )}
                  >
                    {formatP(result.alpha_pvalue)}
                  </TableCell>
                </TableRow>
                {factorNames.map((name) => {
                  const f = result.factors[name];
                  const sig = f.pvalue < 0.05;
                  return (
                    <TableRow key={name}>
                      <TableCell className="pl-4 font-mono text-xs text-muted-foreground">
                        {name}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatCoef(f.coefficient)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {f.t_stat.toFixed(2)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "pr-4 text-right font-mono tabular-nums",
                          sig ? "text-primary" : "text-muted-foreground",
                        )}
                      >
                        {formatP(f.pvalue)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs tabular-nums text-muted-foreground">
            <span>
              R² <span className="text-foreground">{result.r_squared.toFixed(3)}</span>
            </span>
            <span>
              Adj R²{" "}
              <span className="text-foreground">
                {result.adj_r_squared.toFixed(3)}
              </span>
            </span>
            <span>
              n_obs <span className="text-foreground">{result.n_obs}</span>
            </span>
          </div>

          <p className="text-xs text-muted-foreground">
            Alpha after controlling for{" "}
            <span className="font-mono text-foreground">
              {factorNames.join(", ") || "—"}
            </span>{" "}
            is{" "}
            <span
              className={cn(
                "font-mono tabular-nums",
                alphaSignificant && result.alpha >= 0 && "text-profit",
                alphaSignificant && result.alpha < 0 && "text-loss",
                !alphaSignificant && "text-foreground",
              )}
            >
              {formatPct(result.alpha)}
            </span>
            /yr —{" "}
            <span
              className={cn(
                alphaSignificant ? "text-primary" : "text-muted-foreground",
              )}
            >
              {alphaSignificant
                ? "significant at the 5% level"
                : "not significant at the 5% level"}
            </span>
            .
          </p>
        </div>
      )}
    </div>
  );
}
