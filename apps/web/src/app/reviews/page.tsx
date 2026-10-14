"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { Empty, ErrorState, Skeleton, selectClass } from "@/components/bits";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, downloadFile, queryKeys } from "@/lib/api";

export default function Page() {
  return (
    <AppShell>
      <Suspense fallback={<Skeleton className="h-64" />}>
        <Reviews />
      </Suspense>
    </AppShell>
  );
}

function Reviews() {
  const { userId, ready } = useRequireUser();
  const qc = useQueryClient();
  const params = useSearchParams();
  const collections = useQuery({ queryKey: queryKeys.collections(userId), queryFn: api.collections, enabled: ready });
  const reviews = useQuery({ queryKey: queryKeys.reviews(userId), queryFn: api.reviews, enabled: ready });
  const [collection, setCollection] = useState(params.get("collection") ?? "");
  const [topic, setTopic] = useState("");
  const [style, setStyle] = useState<"apa" | "ieee">("apa");
  const [length, setLength] = useState<"short" | "long">("short");
  const [stage, setStage] = useState<string | null>(null);
  const [open, setOpen] = useState<{ jobId: string; md: string } | null>(null);

  const start = useMutation({
    mutationFn: async () => {
      const { job_id } = await api.startReview(collection, topic, style, length);
      for (let i = 0; i < 300; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const j = await api.job(job_id);
        setStage(j.stage ?? j.status);
        if (j.status === "succeeded") return job_id;
        if (j.status === "failed") throw new Error(j.error ?? "The review could not be written.");
      }
      throw new Error("Timed out.");
    },
    onSuccess: async (jobId) => {
      setStage(null);
      void qc.invalidateQueries({ queryKey: queryKeys.reviews(userId) });
      setOpen({ jobId, md: await api.exportReview(jobId, "md") });
    },
    onError: () => setStage(null),
  });

  return (
    <>
      <PageTitle title="Literature reviews" sub="Draft a cited review of a collection: themes, synthesis, APA or IEEE references, BibTeX." />
      <form
        className="mb-8 grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          start.mutate();
        }}
      >
        <label className="flex flex-col gap-1 text-sm">
          Collection
          <select className={selectClass + " h-10"} value={collection} onChange={(e) => setCollection(e.target.value)}>
            <option value="">Choose…</option>
            {collections.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.paper_count})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Topic (optional)
          <Input className="h-10" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. efficient attention" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Citation style
          <select className={selectClass + " h-10"} value={style} onChange={(e) => setStyle(e.target.value as "apa" | "ieee")}>
            <option value="apa">APA (author, year)</option>
            <option value="ieee">IEEE [n]</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Length
          <select className={selectClass + " h-10"} value={length} onChange={(e) => setLength(e.target.value as "short" | "long")}>
            <option value="short">Short</option>
            <option value="long">Long</option>
          </select>
        </label>
        <div className="flex items-center gap-3 sm:col-span-2">
          <Button type="submit" className="h-10" disabled={!collection || start.isPending}>
            {start.isPending && <Loader2 className="animate-spin" aria-hidden />} Draft review
          </Button>
          {stage && <span className="text-sm text-muted-foreground">{stage}…</span>}
          {start.isError && <span className="text-sm text-danger">{(start.error as Error).message}</span>}
        </div>
      </form>

      {open && (
        <section className="mb-8 rounded-xl border border-line bg-surface p-5">
          <div className="mb-3 flex flex-wrap gap-2">
            {(["md", "tex", "bib"] as const).map((f) => (
              <Button key={f} size="sm" variant="outline" onClick={async () => downloadFile(`review.${f}`, await api.exportReview(open.jobId, f))}>
                <Download aria-hidden /> .{f}
              </Button>
            ))}
          </div>
          <Markdown text={open.md} className="font-serif text-[15px]" />
        </section>
      )}

      <h2 className="mb-3 font-semibold">Past drafts</h2>
      {reviews.isPending ? (
        <Skeleton className="h-20" />
      ) : reviews.isError ? (
        <ErrorState error={reviews.error} />
      ) : !reviews.data.length ? (
        <Empty title="No drafts yet">Group 2+ papers into a collection, then draft a review here.</Empty>
      ) : (
        <ul className="grid gap-2">
          {reviews.data.map((r) => (
            <li key={r.id}>
              <button
                className="w-full rounded-xl border border-line bg-surface p-3 text-left hover:border-brand"
                onClick={async () => setOpen({ jobId: r.job_id, md: await api.exportReview(r.job_id, "md") })}
              >
                <p className="font-medium">{r.topic || "Literature review"}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(r.created_at).toLocaleString()} · {r.style.toUpperCase()}
                </p>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
