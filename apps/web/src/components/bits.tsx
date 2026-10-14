"use client";

import { AlertTriangle, CheckCircle2, Loader2, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import type { PaperStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const STAGES: PaperStatus[] = ["queued", "fetching", "parsing", "indexing", "ready"];
const STAGE_LABEL: Record<PaperStatus, string> = {
  queued: "Queued",
  fetching: "Fetching",
  parsing: "Parsing",
  indexing: "Indexing",
  ready: "Ready",
  failed: "Failed",
};

export function StatusPill({ status }: { status: PaperStatus }) {
  if (status === "ready") return null;
  const step = STAGES.indexOf(status);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        status === "failed" ? "bg-danger/10 text-danger" : "bg-brand-soft text-brand",
      )}
    >
      {status === "failed" ? (
        <AlertTriangle className="size-3" aria-hidden />
      ) : (
        <Loader2 className="size-3 animate-spin" aria-hidden />
      )}
      {STAGE_LABEL[status]}
      {status !== "failed" && step >= 0 && <span className="opacity-70">· {step + 1}/4</span>}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function ErrorState({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  const e = error instanceof Error ? error : new Error(String(error));
  const requestId = e instanceof ApiError ? e.requestId : null;
  const quota = e instanceof ApiError && e.code === "quota_exceeded";
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold">{quota ? "Daily limit reached" : (title ?? "Something went wrong")}</h2>
      <p className="text-sm text-muted-foreground">
        {e.message}
        {quota && " Reading, notes and highlights still work."}
      </p>
      <div className="flex gap-2">
        {onRetry && !quota && (
          <Button onClick={onRetry} className="h-10">
            Retry
          </Button>
        )}
        {requestId && (
          <Button variant="outline" className="h-10" onClick={() => void navigator.clipboard.writeText(requestId)}>
            Copy error ID
          </Button>
        )}
      </div>
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-line px-6 py-12 text-center">
      <h2 className="font-semibold">{title}</h2>
      {children && <div className="max-w-md text-sm text-muted-foreground">{children}</div>}
      {action}
    </div>
  );
}

export function Dialog({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center sm:p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "max-h-[92dvh] w-full overflow-auto rounded-t-2xl border border-line bg-surface p-5 shadow-2xl sm:rounded-2xl",
          wide ? "sm:max-w-3xl" : "sm:max-w-lg",
        )}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <X aria-hidden />
          </Button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={cn("flex gap-1 overflow-x-auto", className)}>
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          onClick={() => onChange(t.value)}
          className={cn(
            "h-9 shrink-0 rounded-lg px-3 text-sm font-medium text-muted-foreground hover:text-ink",
            value === t.value && "bg-brand-soft text-ink",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function GroundingBadge({
  grounded,
  score,
  notFound,
}: {
  grounded: boolean | null;
  score: number | null;
  notFound?: boolean;
}) {
  if (notFound) return <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">Not found</span>;
  if (grounded === null || score === null) return null;
  const label = grounded ? "Grounded" : score >= 0.5 ? "Partly grounded" : "Weakly grounded";
  return (
    <span
      title={`${Math.round(score * 100)}% of factual sentences are supported by their cited sources`}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        grounded ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn",
      )}
    >
      {grounded ? <CheckCircle2 className="size-3" aria-hidden /> : <AlertTriangle className="size-3" aria-hidden />}
      {label}
    </span>
  );
}

export const selectClass =
  "h-9 rounded-lg border border-line bg-surface px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";
