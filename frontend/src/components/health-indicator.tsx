"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ShieldCheck, ShieldAlert, Loader2 } from "lucide-react";

export function HealthIndicator() {
  const [status, setStatus] = useState<"ok" | "error" | "loading">("loading");

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await api.health();
        if (res.status === "ok") {
          setStatus("ok");
        } else {
          setStatus("error");
        }
      } catch {
        setStatus("error");
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="mt-auto border-t border-border/60 p-4">
      <div className="flex items-center gap-3 rounded-lg bg-card/40 px-3 py-2 text-xs transition-colors hover:bg-muted/60">
        <div className="flex size-5 items-center justify-center rounded-md bg-muted">
          {status === "loading" && <Loader2 className="size-3 animate-spin text-muted-foreground" />}
          {status === "ok" && <ShieldCheck className="size-3 text-profit" />}
          {status === "error" && <ShieldAlert className="size-3 text-loss" />}
        </div>
        <div className="flex flex-col">
          <span className="font-medium text-foreground">Backend Status</span>
          <span className={cn(
            "text-[10px]",
            status === "loading" && "text-muted-foreground",
            status === "ok" && "text-profit/80",
            status === "error" && "text-loss/80"
          )}>
            {status === "loading" && "Connecting..."}
            {status === "ok" && "System Online"}
            {status === "error" && "System Offline"}
          </span>
        </div>
      </div>
    </div>
  );
}
