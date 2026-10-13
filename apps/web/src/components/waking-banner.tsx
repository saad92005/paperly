"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

const WAKING_AFTER_MS = 3000;

/** Shows "server waking up" when /health is slow (free-tier cold start) and retries until it answers. */
export function WakingBanner() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    retry: true,
    retryDelay: 3000,
    staleTime: 60_000,
  });
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!health.isPending) return;
    const t = setTimeout(() => setSlow(true), WAKING_AFTER_MS);
    return () => clearTimeout(t);
  }, [health.isPending]);

  if (!health.isPending || !slow) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-2 border-b border-line bg-brand-soft px-4 py-2 text-sm text-ink"
    >
      <Loader2 className="size-4 animate-spin" aria-hidden />
      Starting Paperly&apos;s free server… this can take ~30 s the first time.
    </div>
  );
}
