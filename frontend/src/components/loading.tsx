"use client";

import { Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

export function Loading() {
  return (
    <div className="flex h-full w-full items-center justify-center py-20">
      <Loader2 className="size-8 animate-spin text-zinc-500" />
    </div>
  );
}

export function LoadingCard() {
  return (
    <Card className="bg-zinc-900 border-zinc-800">
      <CardHeader>
        <div className="h-4 w-24 animate-pulse rounded bg-zinc-800" />
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div className="h-8 w-32 animate-pulse rounded bg-zinc-800" />
          <div className="h-3 w-20 animate-pulse rounded bg-zinc-800" />
        </div>
      </CardContent>
    </Card>
  );
}
