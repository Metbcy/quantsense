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

/** Skeleton line — configurable width */
function Bone({ className = "w-full" }: { className?: string }) {
  return <div className={`h-4 animate-pulse rounded bg-zinc-800 ${className}`} />;
}

/** Dashboard skeleton: 4 stat cards + chart + table */
export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <LoadingCard key={i} />
        ))}
      </div>
      {/* Chart placeholder */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader>
          <Bone className="w-40" />
        </CardHeader>
        <CardContent>
          <div className="h-64 animate-pulse rounded bg-zinc-800/50" />
        </CardContent>
      </Card>
      {/* Table placeholder */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader>
          <Bone className="w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex gap-4">
              <Bone className="w-16" />
              <Bone className="w-24" />
              <Bone className="w-20" />
              <Bone className="flex-1" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

/** Backtest page skeleton: form + results area */
export function BacktestSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="size-6 animate-pulse rounded bg-zinc-800" />
        <Bone className="w-32 h-6" />
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        {/* Form */}
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader><Bone className="w-28" /></CardHeader>
          <CardContent className="space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Bone className="w-20 h-3" />
                <div className="h-9 animate-pulse rounded bg-zinc-800" />
              </div>
            ))}
            <div className="h-10 animate-pulse rounded bg-zinc-800" />
          </CardContent>
        </Card>
        {/* Results */}
        <div className="space-y-4">
          <Card className="bg-zinc-900 border-zinc-800">
            <CardContent className="py-6">
              <div className="h-48 animate-pulse rounded bg-zinc-800/50" />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

/** Sentiment page skeleton */
export function SentimentSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="size-6 animate-pulse rounded bg-zinc-800" />
        <Bone className="w-32 h-6" />
      </div>
      {/* Search bar */}
      <div className="flex gap-2">
        <div className="h-10 flex-1 animate-pulse rounded bg-zinc-800" />
        <div className="h-10 w-24 animate-pulse rounded bg-zinc-800" />
      </div>
      {/* Score cards */}
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <LoadingCard key={i} />
        ))}
      </div>
      {/* Headlines list */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader><Bone className="w-28" /></CardHeader>
        <CardContent className="space-y-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="space-y-2 border-b border-zinc-800/50 pb-3 last:border-0">
              <Bone className="w-3/4" />
              <Bone className="w-1/2 h-3" />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

/** Settings page skeleton */
export function SettingsSkeleton() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center gap-3">
        <div className="size-6 animate-pulse rounded bg-zinc-800" />
        <Bone className="w-24 h-6" />
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i} className="bg-zinc-900 border-zinc-800">
          <CardHeader>
            <Bone className="w-32" />
            <Bone className="w-48 h-3" />
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="h-9 animate-pulse rounded bg-zinc-800" />
            <div className="h-9 animate-pulse rounded bg-zinc-800" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
