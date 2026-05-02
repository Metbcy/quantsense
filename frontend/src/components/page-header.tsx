import * as React from "react";
import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  /** Small uppercase muted label above the title */
  eyebrow?: React.ReactNode;
  /** Main page title */
  title: React.ReactNode;
  /** Optional one-line description below the title */
  description?: React.ReactNode;
  /** Action area on the right (buttons, controls) */
  actions?: React.ReactNode;
  className?: string;
}

/**
 * PageHeader — top-of-page chrome.
 * Editorial trading terminal: eyebrow / title / description on the left,
 * actions on the right, hairline rule beneath.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-end sm:justify-between sm:gap-6",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-1">
        {eyebrow && (
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {eyebrow}
          </span>
        )}
        <h1 className="text-2xl font-semibold leading-tight tracking-tight text-foreground">
          {title}
        </h1>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </header>
  );
}
