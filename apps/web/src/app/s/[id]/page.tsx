"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense } from "react";

import { ErrorState, Skeleton } from "@/components/bits";
import { Matrix } from "@/components/matrix";
import { api } from "@/lib/api";
import type { CitedText, Comparison, Summary } from "@/lib/types";

const SECTIONS: [keyof Summary, string][] = [
  ["tldr", "TL;DR"], ["problem", "Problem"], ["method", "Method"], ["data", "Data"],
  ["results", "Results"], ["limitations", "Limitations"], ["contributions", "Contributions"],
];

/** Public, read-only share page (no PDF, no notes). */
export default function Page() {
  return (
    <Suspense fallback={null}>
      <SharePage />
    </Suspense>
  );
}

function SharePage() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery({ queryKey: ["share", id], queryFn: () => api.publicShare(id) });
  return (
    <div className="min-h-dvh">
      <header className="flex h-14 items-center justify-between border-b border-line bg-surface px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold"><BookOpen className="size-5 text-brand" aria-hidden /> Paperly</Link>
        <Link href="/login" className="text-sm text-brand">Try Paperly free →</Link>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        {q.isPending ? <Skeleton className="h-64" /> : q.isError ? <ErrorState error={q.error} title="This link isn't available" /> : q.data.kind === "comparison" ? (
          <>
            <h1 className="mb-4 text-2xl font-semibold">{String(q.data.title ?? "Paper comparison")}</h1>
            <Matrix cmp={q.data as unknown as Comparison} />
            <p className="mt-3 text-xs text-muted-foreground">Values extracted by Paperly with page-level citations.</p>
          </>
        ) : (
          <SummaryView data={q.data as { paper: { title: string; authors: string[]; year: number | null; venue: string | null; arxiv_id: string | null; doi: string | null }; summary: Summary | null }} />
        )}
      </main>
    </div>
  );
}

function SummaryView({ data }: { data: { paper: { title: string; authors: string[]; year: number | null; venue: string | null; arxiv_id: string | null; doi: string | null }; summary: Summary | null } }) {
  const p = data.paper;
  const link = p.arxiv_id ? `https://arxiv.org/abs/${p.arxiv_id}` : p.doi ? `https://doi.org/${p.doi}` : null;
  return (
    <article className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">{p.title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        {p.authors.slice(0, 6).join(", ")} · {p.year} {p.venue ? `· ${p.venue}` : ""}
        {link && <> · <a className="text-brand underline" href={link} target="_blank" rel="noopener noreferrer">Original paper</a></>}
      </p>
      {!data.summary ? <p className="mt-6 text-muted-foreground">No summary yet.</p> : SECTIONS.map(([k, label]) => {
        const items = (data.summary![k] as CitedText[]) ?? [];
        if (!items.length) return null;
        return (
          <section key={k} className="mt-6">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h2>
            <ul className="flex list-disc flex-col gap-2 pl-5 font-serif text-[16px] leading-relaxed">
              {items.map((it, i) => (
                <li key={i}>
                  {it.text} <span className="text-xs text-muted-foreground">{it.citations.map((c) => `p.${c.page}`).join(", ")}</span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </article>
  );
}
