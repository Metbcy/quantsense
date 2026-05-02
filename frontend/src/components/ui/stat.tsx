import * as React from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StatProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Uppercase eyebrow label */
  label: string;
  /** Headline value (already formatted) */
  value: React.ReactNode;
  /** Optional secondary line beneath the value */
  sub?: React.ReactNode;
  /**
   * Optional trend signal — positive renders profit color + up arrow,
   * negative renders loss color + down arrow, null/undefined = neutral.
   */
  trend?: number | null;
}

/**
 * Stat — KPI primitive.
 * Mono numerals, tabular alignment, uppercase label, optional trend arrow.
 * Used across dashboard, backtest, compare. No card chrome — wrap as needed.
 */
export function Stat({
  label,
  value,
  sub,
  trend,
  className,
  ...props
}: StatProps) {
  const direction =
    typeof trend === "number" ? (trend > 0 ? "up" : trend < 0 ? "down" : "flat") : "none";
  const trendColor =
    direction === "up"
      ? "text-profit"
      : direction === "down"
        ? "text-loss"
        : "text-muted-foreground";

  return (
    <div className={cn("flex flex-col gap-1.5", className)} {...props}>
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-2xl font-semibold leading-none tracking-tight tabular-nums text-foreground">
        {value}
      </span>
      {(sub !== undefined || direction !== "none") && (
        <div className={cn("flex items-center gap-1 font-mono text-xs tabular-nums", trendColor)}>
          {direction === "up" && <ArrowUpRight className="size-3.5" aria-hidden />}
          {direction === "down" && <ArrowDownRight className="size-3.5" aria-hidden />}
          {sub !== undefined && <span>{sub}</span>}
        </div>
      )}
    </div>
  );
}
