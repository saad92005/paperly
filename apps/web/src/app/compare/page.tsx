"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Columns3, Loader2, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { Empty, ErrorState, Skeleton } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { api, queryKeys } from "@/lib/api";

export default function ComparePage() {
  const { userId, ready } = useRequireUser();
  const router = useRouter();
  const qc = useQueryClient();
  const [picked, setPicked] = useState<string[]>([]);
  const papers = useQuery({ queryKey: queryKeys.papers(userId), queryFn: () => api.papers(), enabled: ready });
  const list = useQuery({ queryKey: queryKeys.comparisons(userId), queryFn: api.comparisons, enabled: ready });
  const create = useMutation({
    mutationFn: () => api.createComparison(picked),
    onSuccess: (r) => router.push(`/compare/${r.comparison_id}`),
  });
  const readyPapers = papers.data?.items.filter((p) => p.status === "ready") ?? [];

  return (
    <AppShell>
      <PageTitle title="Compare papers" sub="Build a cited matrix: task, method, data, metrics, results, compute, limitations, code." />
      <section className="mb-8 rounded-xl border border-line bg-surface p-4">
        <h2 className="mb-3 font-semibold">New comparison</h2>
        {papers.isPending ? (
          <Skeleton className="h-20" />
        ) : readyPapers.length < 2 ? (
          <p className="text-sm text-muted-foreground">
            Add at least two papers to your <Link className="text-brand underline" href="/library">library</Link> first.
          </p>
        ) : (
          <>
            <div className="flex max-h-64 flex-col gap-1 overflow-auto">
              {readyPapers.map((p) => (
                <label key={p.id} className="flex min-h-10 cursor-pointer items-center gap-3 rounded-lg px-2 hover:bg-brand-soft">
                  <input
                    type="checkbox"
                    checked={picked.includes(p.id)}
                    disabled={!picked.includes(p.id) && picked.length >= 10}
                    onChange={(e) => setPicked((x) => (e.target.checked ? [...x, p.id] : x.filter((y) => y !== p.id)))}
                  />
                  <span className="text-sm">{p.title ?? "Untitled"}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{p.year}</span>
                </label>
              ))}
            </div>
            {create.isError && <p className="mt-2 text-sm text-danger">{(create.error as Error).message}</p>}
            <Button className="mt-3 h-10" disabled={picked.length < 2 || create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Columns3 aria-hidden />} Compare {picked.length || ""} papers
            </Button>
          </>
        )}
      </section>

      <h2 className="mb-3 font-semibold">Your comparisons</h2>
      {list.isPending ? (
        <Skeleton className="h-24" />
      ) : list.isError ? (
        <ErrorState error={list.error} onRetry={() => void list.refetch()} />
      ) : !list.data.length ? (
        <Empty title="No comparisons yet">Pick two or more papers above.</Empty>
      ) : (
        <ul className="grid gap-3">
          {list.data.map((c) => (
            <li key={c.id} className="flex items-center gap-3 rounded-xl border border-line bg-surface p-4">
              <Link href={`/compare/${c.id}`} className="min-w-0 flex-1">
                <p className="truncate font-medium">{c.title ?? c.papers.map((p) => p.title?.split(":")[0]).join(" vs ")}</p>
                <p className="text-xs text-muted-foreground">
                  {c.papers.length} papers · {c.columns.length} columns · {c.status}
                </p>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Delete comparison"
                onClick={async () => {
                  await api.deleteComparison(c.id);
                  void qc.invalidateQueries({ queryKey: queryKeys.comparisons(userId) });
                }}
              >
                <Trash2 aria-hidden />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </AppShell>
  );
}
