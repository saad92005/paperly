"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Loader2, RefreshCw, Share2, Trash2, Volume2 } from "lucide-react";
import { useState } from "react";

import { Empty, ErrorState, Skeleton, selectClass } from "@/components/bits";
import { CitationChip, Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { api, downloadFile, downloadFromApi, queryKeys } from "@/lib/api";
import type { Citation, CitedText, Level, Note, Paper, Summary } from "@/lib/types";
import { cn } from "@/lib/utils";

const SECTIONS: [keyof Summary, string][] = [
  ["tldr", "TL;DR"],
  ["problem", "Problem"],
  ["method", "Method"],
  ["data", "Data"],
  ["results", "Results"],
  ["limitations", "Limitations"],
  ["contributions", "Contributions"],
];

function summaryMarkdown(s: Summary, title: string): string {
  const out = [`# ${title}`, ""];
  for (const [k, label] of SECTIONS) {
    const items = s[k] as CitedText[];
    if (!items?.length) continue;
    out.push(`## ${label}`);
    for (const it of items) out.push(`- ${it.text} ${it.citations.map((c) => `(p.${c.page})`).join(" ")}`);
    out.push("");
  }
  if (s.keywords?.length) out.push(`**Keywords:** ${s.keywords.join(", ")}`);
  return out.join("\n");
}

export function SummaryPanel({ userId, paper, onCite }: { userId: string; paper: Paper; onCite: (c: Citation) => void }) {
  const [level, setLevel] = useState<Level>("student");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: queryKeys.summary(userId, paper.id, level),
    queryFn: () => api.summary(paper.id, level),
    staleTime: Infinity,
    retry: 1,
  });
  const regen = useMutation({
    mutationFn: async () => {
      const { job_id } = await api.regenerateSummary(paper.id, level);
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const j = await api.job(job_id);
        if (j.status === "succeeded") return;
        if (j.status === "failed") throw new Error(j.error ?? "Regeneration failed.");
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.summary(userId, paper.id, level) }),
  });

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Level" className={selectClass} value={level} onChange={(e) => setLevel(e.target.value as Level)}>
          <option value="eli5">ELI5</option>
          <option value="student">Student</option>
          <option value="expert">Expert</option>
        </select>
        <Button size="sm" variant="outline" disabled={regen.isPending || !q.data} onClick={() => regen.mutate()}>
          {regen.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />} Regenerate
        </Button>
        <Button size="sm" variant="ghost" disabled={!q.data} onClick={() => q.data && void navigator.clipboard.writeText(summaryMarkdown(q.data, paper.title ?? "Paper"))}>
          <Copy aria-hidden /> Copy
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!q.data}
          onClick={async () => {
            const r = await api.share("summary", paper.id);
            setShareUrl(r.url);
            void navigator.clipboard.writeText(r.url);
          }}
        >
          <Share2 aria-hidden /> Share
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!q.data}
          aria-label="Listen"
          onClick={() => {
            if (!q.data) return;
            speechSynthesis.cancel();
            const text = SECTIONS.flatMap(([k, l]) => [l + ".", ...((q.data[k] as CitedText[]) ?? []).map((i) => i.text)]).join(" ");
            speechSynthesis.speak(new SpeechSynthesisUtterance(text));
          }}
        >
          <Volume2 aria-hidden /> Listen
        </Button>
      </div>
      {shareUrl && (
        <p className="rounded-lg bg-brand-soft px-3 py-2 text-xs">
          Link copied: <a className="underline" href={shareUrl} target="_blank" rel="noreferrer">{shareUrl}</a>
        </p>
      )}
      {regen.isError && <p className="text-sm text-danger">{(regen.error as Error).message}</p>}
      {q.isPending ? (
        <div className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">Writing a cited summary (first time ≈ 10–20 s)…</p>
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
        </div>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      ) : (
        <>
          {q.data.extractive && (
            <p className="rounded-lg bg-warn/10 px-3 py-2 text-xs text-warn">
              Extractive summary: key sentences quoted from the paper. Add a free AI key for a written summary.
            </p>
          )}
          {SECTIONS.map(([k, label]) => {
            const items = (q.data[k] as CitedText[]) ?? [];
            if (!items.length) return null;
            return (
              <section key={k} className="rounded-xl border border-line bg-surface p-4">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h3>
                <ul className="flex flex-col gap-2 font-serif text-[15px] leading-relaxed">
                  {items.map((it, i) => (
                    <li key={i} dir="auto">
                      {it.text}
                      {it.citations.map((c, j) => (
                        <CitationChip key={j} c={{ ...c, n: j + 1 }} n={j + 1} onClick={onCite} />
                      ))}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
          {!!q.data.keywords?.length && (
            <div className="flex flex-wrap gap-1">
              {q.data.keywords.map((k) => (
                <span key={k} className="rounded-full bg-brand-soft px-2 py-0.5 text-xs">{k}</span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

const COLORS: Note["color"][] = ["yellow", "green", "blue", "pink", "purple"];
const SWATCH: Record<Note["color"], string> = {
  yellow: "bg-hl-yellow", green: "bg-hl-green", blue: "bg-hl-blue", pink: "bg-hl-pink", purple: "bg-brand-soft",
};

export function NotesPanel({
  userId,
  paper,
  notes,
  onJump,
}: {
  userId: string;
  paper: Paper;
  notes: Note[];
  onJump: (n: Note) => void;
}) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const refresh = () => void qc.invalidateQueries({ queryKey: queryKeys.notes(userId, paper.id) });

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={async () => downloadFile(`${(paper.title ?? "notes").slice(0, 40)}-notes.md`, await api.exportNotes(paper.id), "text/markdown")}>
          <Download aria-hidden /> Export Markdown
        </Button>
      </div>
      <form
        className="flex flex-col gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!draft.trim()) return;
          await api.createNote(paper.id, { anchor: null, body_md: draft, color: "yellow" });
          setDraft("");
          refresh();
        }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          placeholder="Add a general note… (select text in the PDF to anchor a note)"
          aria-label="New note"
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button type="submit" size="sm" className="self-end" disabled={!draft.trim()}>Add note</Button>
      </form>
      {notes.length === 0 ? (
        <Empty title="No notes yet">Select text in the paper and choose Highlight or Note. Answers can be saved here too.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {notes.map((n) => (
            <NoteItem key={n.id} n={n} onJump={() => onJump(n)} onChange={refresh} />
          ))}
        </ul>
      )}
    </div>
  );
}

function NoteItem({ n, onJump, onChange }: { n: Note; onJump: () => void; onChange: () => void }) {
  const [edit, setEdit] = useState(false);
  const [body, setBody] = useState(n.body_md);
  return (
    <li className="rounded-xl border border-line bg-surface p-3 text-sm">
      <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
        <span className={cn("size-3 rounded-full", SWATCH[n.color])} />
        {n.anchor ? (
          <button className="hover:text-brand" onClick={onJump}>p.{n.anchor.page}</button>
        ) : (
          <span>General</span>
        )}
        {n.origin === "ai" && <span className="rounded bg-brand-soft px-1">AI</span>}
        <span className="ml-auto flex gap-1">
          {COLORS.map((c) => (
            <button
              key={c}
              aria-label={`Colour ${c}`}
              className={cn("size-3.5 rounded-full border border-line", SWATCH[c])}
              onClick={async () => {
                await api.updateNote(n.id, { color: c });
                onChange();
              }}
            />
          ))}
          <button aria-label="Delete note" className="ml-1 hover:text-danger" onClick={async () => { await api.deleteNote(n.id); onChange(); }}>
            <Trash2 className="size-3.5" aria-hidden />
          </button>
        </span>
      </div>
      {n.anchor?.text && <blockquote className="mb-1 border-l-2 border-line pl-2 text-xs text-muted-foreground">{n.anchor.text.slice(0, 300)}</blockquote>}
      {edit ? (
        <div className="flex flex-col gap-1">
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} aria-label="Edit note" className="rounded-lg border border-line bg-surface px-2 py-1" />
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="ghost" onClick={() => setEdit(false)}>Cancel</Button>
            <Button size="sm" onClick={async () => { await api.updateNote(n.id, { body_md: body }); setEdit(false); onChange(); }}>Save</Button>
          </div>
        </div>
      ) : (
        <button className="w-full text-left" onClick={() => setEdit(true)} aria-label="Edit note">
          {n.body_md ? <Markdown text={n.body_md} className="text-sm" /> : <span className="text-xs text-muted-foreground">Add a comment…</span>}
        </button>
      )}
    </li>
  );
}

export function GlossaryPanel({ userId, paper, onCite }: { userId: string; paper: Paper; onCite: (c: Citation) => void }) {
  const q = useQuery({ queryKey: queryKeys.glossary(userId, paper.id), queryFn: () => api.glossary(paper.id), staleTime: Infinity, retry: 0 });
  if (q.isPending)
    return (
      <div className="flex flex-col gap-2 p-4">
        <p className="text-xs text-muted-foreground">Extracting key terms…</p>
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10" />)}
      </div>
    );
  if (q.isError) return <div className="p-4"><ErrorState error={q.error} onRetry={() => void q.refetch()} /></div>;
  return (
    <dl className="flex flex-col gap-3 p-4 text-sm">
      {q.data.terms.map((t) => (
        <div key={t.term} className="rounded-xl border border-line bg-surface p-3">
          <dt className="font-semibold">
            {t.term}
            {t.citations.slice(0, 1).map((c) => <CitationChip key={c.chunk_id} c={{ ...c, n: 1 }} n={1} onClick={onCite} />)}
          </dt>
          <dd className="text-muted-foreground">{t.definition}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ReferencesPanel({ userId, paper }: { userId: string; paper: Paper }) {
  const qc = useQueryClient();
  const refs = useQuery({ queryKey: queryKeys.references(userId, paper.id), queryFn: () => api.references(paper.id) });
  const cited = useQuery({ queryKey: queryKeys.citedBy(userId, paper.id), queryFn: () => api.citedBy(paper.id), enabled: !!(paper.arxiv_id || paper.doi), staleTime: Infinity });
  const [added, setAdded] = useState<Record<string, string>>({});
  async function add(key: string, source: "arxiv" | "doi", value: string) {
    setAdded((a) => ({ ...a, [key]: "Adding…" }));
    try {
      await api.importPaper(source, value);
      setAdded((a) => ({ ...a, [key]: "Added" }));
      void qc.invalidateQueries({ queryKey: ["papers"] });
    } catch (e) {
      setAdded((a) => ({ ...a, [key]: (e as Error).message }));
    }
  }
  return (
    <div className="flex flex-col gap-5 p-4 text-sm">
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cite this paper</h3>
        <div className="flex flex-wrap gap-2">
          {(["bibtex", "apa", "ieee"] as const).map((s) => (
            <Button key={s} size="sm" variant="outline" onClick={async () => void navigator.clipboard.writeText(await api.cite(paper.id, s))}>
              <Copy aria-hidden /> {s.toUpperCase()}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => void downloadFromApi(`/v1/papers/${paper.id}/bibtex?style=bibtex`, "paper.bib")}>
            <Download aria-hidden /> .bib
          </Button>
        </div>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">References ({refs.data?.length ?? "…"})</h3>
        {refs.isPending ? <Skeleton className="h-24" /> : (
          <ol className="flex flex-col gap-2">
            {refs.data?.map((r) => {
              const key = `r${r.idx}`;
              return (
                <li key={r.idx} className="flex gap-2">
                  <span className="min-w-0 flex-1 text-muted-foreground">{r.raw}</span>
                  {r.in_library ? <span className="shrink-0 text-xs text-ok">In library</span> : (r.arxiv_id || r.doi) && (
                    <Button size="xs" variant="outline" disabled={!!added[key]} onClick={() => void add(key, r.arxiv_id ? "arxiv" : "doi", (r.arxiv_id ?? r.doi)!)}>
                      {added[key] ?? "Import"}
                    </Button>
                  )}
                </li>
              );
            })}
            {refs.data?.length === 0 && <p className="text-muted-foreground">No references were detected.</p>}
          </ol>
        )}
      </section>
      {(paper.arxiv_id || paper.doi) && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cited by (Semantic Scholar)</h3>
          {cited.isPending ? <Skeleton className="h-16" /> : cited.isError ? <p className="text-muted-foreground">Unavailable right now.</p> : (
            <ul className="flex flex-col gap-2">
              {cited.data?.map((c, i) => (
                <li key={i} className="flex gap-2">
                  <span className="min-w-0 flex-1">{c.title} <span className="text-muted-foreground">· {c.year ?? ""}</span></span>
                  {c.arxiv_id && (
                    <Button size="xs" variant="outline" disabled={!!added[`c${i}`]} onClick={() => void add(`c${i}`, "arxiv", c.arxiv_id!)}>
                      {added[`c${i}`] ?? "Import"}
                    </Button>
                  )}
                </li>
              ))}
              {cited.data?.length === 0 && <p className="text-muted-foreground">No citing papers found.</p>}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

export function CardsPanel({ userId, paper, onCite }: { userId: string; paper: Paper; onCite: (c: Citation) => void }) {
  const qc = useQueryClient();
  const cards = useQuery({ queryKey: queryKeys.cards(userId, paper.id), queryFn: () => api.cards(paper.id) });
  const make = useMutation({
    mutationFn: async () => {
      const { job_id } = await api.makeCards(paper.id, 10);
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const j = await api.job(job_id);
        if (j.status === "succeeded") return;
        if (j.status === "failed") throw new Error(j.error ?? "Couldn't create cards.");
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.cards(userId, paper.id) }),
  });
  return (
    <div className="flex flex-col gap-3 p-4 text-sm">
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={make.isPending} onClick={() => make.mutate()}>
          {make.isPending && <Loader2 className="animate-spin" aria-hidden />} Generate 10 flashcards
        </Button>
        {!!cards.data?.length && (
          <Button size="sm" variant="outline" onClick={() => void downloadFromApi(`/v1/papers/${paper.id}/flashcards/anki`, "paperly-anki.txt")}>
            <Download aria-hidden /> Anki export
          </Button>
        )}
      </div>
      {make.isError && <p className="text-danger">{(make.error as Error).message}</p>}
      {cards.data?.length === 0 && !make.isPending && <Empty title="No flashcards yet">Generate cited cards, then review them in Study.</Empty>}
      <ul className="flex flex-col gap-2">
        {cards.data?.map((c) => (
          <li key={c.id} className="rounded-xl border border-line bg-surface p-3">
            <p className="font-medium">{c.front}</p>
            <p className="mt-1 text-muted-foreground">
              {c.back}
              {c.citation && <CitationChip c={{ ...c.citation, n: 1 }} n={1} onClick={onCite} />}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
