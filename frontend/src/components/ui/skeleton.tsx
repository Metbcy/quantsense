import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Skeleton — bordered animated placeholder block.
 * Editorial trading terminal: hairline border + subtle pulse, no spinner.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "animate-pulse rounded-md border border-border bg-muted/40",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
