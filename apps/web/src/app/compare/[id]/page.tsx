"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Plus, Share2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { Dialog, ErrorState, Skeleton } from "@/components/bits";
import { Matrix } from "@/components/matrix";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, downloadFromApi, kickWorker, queryKeys } from "@/lib/api";

const SUGGESTIONS: [string, string][] = [
  ["Dataset size", "How large are the datasets used (number of examples/tokens)?"],
  ["Best metric", "What is the single best reported metric value and on which benchmark?"],
  ["Model size", "How many parameters does the main model have?"],
  ["Baselines", "Which baselines are compared against?"],
];

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ComparisonView />
    </Suspense>
  );
}

function ComparisonView() {
  const { id } = useParams<{ id: string }>();
  const { userId, ready } = useRequireUser();
  const router = useRouter();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [label, setLabel] = useState("");
  const [question, setQuestion] = useState("");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const q = useQuery({
    queryKey: queryKeys.comparison(userId, id),
    queryFn: () => api.comparison(id),
    enabled: ready,
    refetchInterval: (query) => {
      const pending = !!query.state.data && ["queued", "running"].includes(query.state.data.status);
      if (pending) kickWorker();
      return pending ? 2000 : false;
    },
  });
  const add = useMutation({
    mutationFn: () => api.addColumn(id, label.trim(), question.trim()),
    onSuccess: () => {
      setAdding(false);
      setLabel("");
      setQuestion("");
      void qc.invalidateQueries({ queryKey: queryKeys.comparison(userId, id) });
    },
  });

  return (
    <AppShell>
      <Link href="/compare" className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden /> Comparisons
      </Link>
      {q.isPending ? (
        <Skeleton className="h-64" />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : (
        <>
          <PageTitle
            title={q.data.title ?? "Comparison"}
            sub={["queued", "running"].includes(q.data.status) ? "Reading each paper and filling cells…" : `${q.data.papers.length} papers · every cell cites its sentence`}
          >
            <Button variant="outline" className="h-10" onClick={() => setAdding(true)}>
              <Plus aria-hidden /> Add column
            </Button>
            {(["csv", "xlsx", "md"] as const).map((f) => (
              <Button key={f} variant="ghost" className="h-10" onClick={() => void downloadFromApi(`/v1/comparisons/${id}/export?format=${f}`, `comparison.${f}`)}>
                <Download aria-hidden /> {f.toUpperCase()}
              </Button>
            ))}
            <Button
              variant="ghost"
              className="h-10"
              onClick={async () => {
                const r = await api.share("comparison", id);
                setShareUrl(r.url);
                void navigator.clipboard.writeText(r.url);
              }}
            >
              <Share2 aria-hidden /> Share
            </Button>
          </PageTitle>
          {shareUrl && <p className="mb-3 rounded-lg bg-brand-soft px-3 py-2 text-xs">Link copied: <a className="underline" href={shareUrl}>{shareUrl}</a></p>}
          {q.data.status === "failed" && <p className="mb-3 text-sm text-danger">Some cells could not be filled. Try adding the column again later.</p>}
          <Matrix cmp={q.data} running={["queued", "running"].includes(q.data.status)} onCite={(c) => router.push(`/paper/${c.paper_id}?page=${c.page}`)} />
        </>
      )}
      <Dialog open={adding} onClose={() => setAdding(false)} title="Add a column">
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <div className="flex flex-wrap gap-1">
            {SUGGESTIONS.map(([l, qq]) => (
              <button key={l} type="button" className="rounded-full border border-line px-2 py-0.5 text-xs hover:border-brand" onClick={() => { setLabel(l); setQuestion(qq); }}>
                {l}
              </button>
            ))}
          </div>
          <Input aria-label="Column label" placeholder="Label (e.g. Dataset size)" className="h-10" value={label} onChange={(e) => setLabel(e.target.value)} />
          <Input aria-label="Question" placeholder="Question to ask each paper" className="h-10" value={question} onChange={(e) => setQuestion(e.target.value)} />
          {add.isError && <p className="text-sm text-danger">{(add.error as Error).message}</p>}
          <Button type="submit" className="h-10" disabled={!label.trim() || question.trim().length < 3 || add.isPending}>Add and fill</Button>
        </form>
      </Dialog>
    </AppShell>
  );
}
