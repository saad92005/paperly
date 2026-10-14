"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { useRequireUser } from "@/components/app-shell";
import { selectClass } from "@/components/bits";
import { PdfViewer, type Highlight } from "@/components/reader/pdf-viewer";
import { api, queryKeys } from "@/lib/api";

const KIND_COLOR: Record<string, Highlight["kind"]> = {
  abstract: "green",
  body: "blue",
  caption: "yellow",
  reference: "pink",
  table: "purple",
  equation: "purple",
};

/** Dev view: overlays chunk and sentence boxes on the PDF to inspect parsing quality. */
export default function Page() {
  return (
    <Suspense fallback={null}>
      <DebugView />
    </Suspense>
  );
}

function DebugView() {
  const { id } = useParams<{ id: string }>();
  const { userId, ready } = useRequireUser();
  const [mode, setMode] = useState<"sentences" | "chunks">("sentences");
  const [selected, setSelected] = useState<string | null>(null);
  const chunks = useQuery({ queryKey: queryKeys.chunks(userId, id), queryFn: () => api.chunks(id), enabled: ready });
  const file = useQuery({ queryKey: ["file", userId, id], queryFn: () => api.paperFile(id), enabled: ready, staleTime: Infinity });

  const highlights = useMemo<Highlight[]>(() => {
    const out: Highlight[] = [];
    for (const c of chunks.data ?? []) {
      if (selected && c.id !== selected) continue;
      c.sentences.forEach((s, si) =>
        s.rects.forEach((r, ri) =>
          out.push({
            id: `${c.id}-${si}-${ri}`,
            page: r[0],
            rect: [r[1], r[2], r[3], r[4]],
            kind: mode === "chunks" ? KIND_COLOR[c.kind] ?? "blue" : si % 2 ? "green" : "blue",
            title: `#${c.idx} ${c.kind} · ${c.section ?? ""}`,
          }),
        ),
      );
    }
    return out;
  }, [chunks.data, mode, selected]);

  const counts = (chunks.data ?? []).reduce<Record<string, number>>((a, c) => ((a[c.kind] = (a[c.kind] ?? 0) + 1), a), {});

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface px-3 text-sm">
        <Link href={`/paper/${id}`} className="text-muted-foreground hover:text-ink">← Reader</Link>
        <span className="font-semibold">Parser debug</span>
        <select aria-label="Overlay" className={selectClass} value={mode} onChange={(e) => setMode(e.target.value as "sentences" | "chunks")}>
          <option value="sentences">Sentence boxes</option>
          <option value="chunks">Chunks by kind</option>
        </select>
        <span className="text-xs text-muted-foreground">
          {chunks.data?.length ?? "…"} chunks · {Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ")}
        </span>
      </header>
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          {file.data && <PdfViewer data={file.data} zoom={1.2} highlights={highlights} onSelection={() => undefined} onPage={() => undefined} />}
        </div>
        <ol className="w-96 shrink-0 overflow-auto border-l border-line bg-surface p-2 text-xs">
          {chunks.data?.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => setSelected(selected === c.id ? null : c.id)}
                className={`mb-1 w-full rounded-lg border p-2 text-left ${selected === c.id ? "border-brand bg-brand-soft" : "border-line"}`}
              >
                <div className="font-mono text-[10px] text-muted-foreground">
                  #{c.idx} · {c.kind} · p.{c.page_start}–{c.page_end} · {c.token_count} tok · {c.sentences.length} sent
                </div>
                <div className="font-medium">{c.section}</div>
                <div className="line-clamp-3 text-muted-foreground">{c.text}</div>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
