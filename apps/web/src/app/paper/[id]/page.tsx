"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Bug,
  FileText,
  Highlighter,
  Languages,
  Lightbulb,
  ListTree,
  Loader2,
  MessageSquare,
  Minus,
  NotebookPen,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Search,
  Sigma,
  Sparkles,
  Star,
  X,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useRequireUser } from "@/components/app-shell";
import { ErrorState, Skeleton, Tabs } from "@/components/bits";
import { Markdown } from "@/components/markdown";
import { ChatPanel } from "@/components/reader/chat-panel";
import { PdfViewer, type Highlight, type PdfViewerHandle, type SelectionInfo } from "@/components/reader/pdf-viewer";
import { CardsPanel, GlossaryPanel, NotesPanel, ReferencesPanel, SummaryPanel } from "@/components/reader/side-panels";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, queryKeys } from "@/lib/api";
import { streamSse } from "@/lib/sse";
import type { Citation, Note } from "@/lib/types";
import { cn } from "@/lib/utils";

type PanelTab = "chat" | "summary" | "notes" | "glossary" | "refs" | "cards";
type MobileTab = "paper" | "ask" | "notes";
type Explain = { kind: "explain" | "simplify" | "translate" | "equation"; text: string; page: number; out: string; cites: Citation[]; busy: boolean; error?: string };

export default function Page() {
  return (
    <Suspense fallback={<div className="h-dvh animate-pulse bg-muted/40" />}>
      <ReaderPage />
    </Suspense>
  );
}

function ReaderPage() {
  const { id } = useParams<{ id: string }>();
  const { userId, ready } = useRequireUser();
  const qc = useQueryClient();
  const viewer = useRef<PdfViewerHandle>(null);
  const askRef = useRef<((q: string, sel?: { page: number; text: string }) => void) | null>(null);

  const paper = useQuery({ queryKey: queryKeys.paper(userId, id), queryFn: () => api.paper(id), enabled: ready });
  const file = useQuery({
    queryKey: ["file", userId, id],
    queryFn: () => api.paperFile(id),
    enabled: ready && paper.data?.status === "ready",
    staleTime: Infinity,
  });
  const notes = useQuery({ queryKey: queryKeys.notes(userId, id), queryFn: () => api.notes(id), enabled: ready });

  const [zoom, setZoom] = useState(1.25);
  const [page, setPage] = useState({ n: 1, of: 0 });
  const [tab, setTab] = useState<PanelTab>("chat");
  const [mobile, setMobile] = useState<MobileTab>("paper");
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelW, setPanelW] = useState(440);
  const [outline, setOutline] = useState(true);
  const [cite, setCite] = useState<{ c: Citation; token: number } | null>(null);
  const [answerCites, setAnswerCites] = useState<Citation[]>([]);
  const [sel, setSel] = useState<SelectionInfo | null>(null);
  const [explain, setExplain] = useState<Explain | null>(null);
  const [find, setFind] = useState("");
  const [findHits, setFindHits] = useState<number[] | null>(null);

  // Remember panel width per device.
  useEffect(() => {
    try {
      const w = Number(localStorage.getItem("paperly.panelW"));
      if (w >= 360 && w <= 900) setPanelW(w);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const onPage = useCallback((n: number, of: number) => setPage({ n, of }), []);
  const search = useSearchParams();
  const startPage = Number(search.get("page")) || 0;
  const fitMobile = useCallback(() => {
    if (window.innerWidth < 768) setZoom(Math.max(0.5, (window.innerWidth - 24) / 612));
    if (startPage > 1) setTimeout(() => viewer.current?.scrollTo(startPage), 300);
  }, [startPage]);

  const jump = useCallback((c: Citation) => {
    setCite({ c, token: Date.now() });
    setMobile("paper");
  }, []);

  // When a citation is chosen: fetch exact rects if missing, then scroll there.
  useEffect(() => {
    if (!cite) return;
    let alive = true;
    (async () => {
      let rects = cite.c.rects;
      if (!rects.length && cite.c.chunk_id && cite.c.paper_id === id) {
        try {
          const ch = await (await import("@/lib/api")).apiFetch<{ sentences: { page: number; rects: number[][] }[] }>(
            `/v1/papers/${id}/chunks/${cite.c.chunk_id}`,
          );
          const ss = cite.c.sentence_idx.length ? cite.c.sentence_idx.map((i) => ch.sentences[i]).filter(Boolean) : ch.sentences.slice(0, 1);
          rects = ss.flatMap((s) => s.rects.map((r) => ({ page: r[0], rect: [r[1], r[2], r[3], r[4]] as [number, number, number, number] })));
          if (alive) setCite((x) => (x && x.token === cite.token ? { ...x, c: { ...x.c, rects } } : x));
        } catch {
          /* fall back to the page */
        }
      }
      if (!alive) return;
      const first = rects[0];
      viewer.current?.scrollTo(first?.page ?? cite.c.page, first?.rect);
    })();
    return () => {
      alive = false;
    };
  }, [cite?.token]); // eslint-disable-line react-hooks/exhaustive-deps

  const highlights = useMemo<Highlight[]>(() => {
    const out: Highlight[] = [];
    for (const n of notes.data ?? []) {
      if (!n.anchor) continue;
      n.anchor.rects.forEach((r, i) =>
        out.push({ id: `${n.id}-${i}`, page: n.anchor!.page, rect: r as Highlight["rect"], kind: n.color, title: n.body_md.slice(0, 120) }),
      );
    }
    if (cite && cite.c.paper_id === id)
      cite.c.rects.forEach((r, i) => out.push({ id: `cite-${cite.token}-${i}`, page: r.page, rect: r.rect, kind: "cite", pulse: true }));
    return out;
  }, [notes.data, cite, id]);

  // Persist reading progress (debounced).
  useEffect(() => {
    if (!page.of || !ready) return;
    const t = setTimeout(() => {
      const p = Math.min(1, page.n / page.of);
      if (p > (paper.data?.read_progress ?? 0) + 0.04) void api.updatePaper(id, { read_progress: p }).catch(() => undefined);
    }, 1500);
    return () => clearTimeout(t);
  }, [page, id, ready, paper.data?.read_progress]);

  const addNote = useCallback(
    async (color: Note["color"], body = "") => {
      if (!sel) return;
      await api.createNote(id, { anchor: { page: sel.page, rects: sel.rects, text: sel.text }, body_md: body, color });
      window.getSelection()?.removeAllRanges();
      setSel(null);
      void qc.invalidateQueries({ queryKey: queryKeys.notes(userId, id) });
    },
    [sel, id, qc, userId],
  );

  const runExplain = useCallback(
    async (kind: Explain["kind"]) => {
      if (!sel) return;
      const base: Explain = { kind, text: sel.text, page: sel.page, out: "", cites: [], busy: true };
      setExplain(base);
      setSel(null);
      try {
        const body = { text: sel.text, page: sel.page, kind, lang: kind === "translate" ? (navigator.language.slice(0, 2) === "en" ? "es" : navigator.language.slice(0, 2)) : "en", level: "student" };
        for await (const ev of streamSse(`/v1/papers/${id}/explain`, { method: "POST", body: JSON.stringify(body) })) {
          if (ev.event === "token") setExplain((e) => e && { ...e, out: e.out + String(ev.data.t) });
          else if (ev.event === "citation") setExplain((e) => e && { ...e, cites: [...e.cites, ev.data as unknown as Citation] });
          else if (ev.event === "error") setExplain((e) => e && { ...e, error: String(ev.data.message) });
        }
      } catch (e) {
        setExplain((x) => x && { ...x, error: (e as Error).message });
      } finally {
        setExplain((e) => e && { ...e, busy: false });
      }
    },
    [sel, id],
  );

  // Keyboard shortcuts (docs/05 §6).
  useEffect(() => {
    let lastG = 0;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (/INPUT|TEXTAREA|SELECT/.test(t.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "]") setPanelOpen((o) => !o);
      else if ((e.key === "j" || e.key === "k") && answerCites.length) {
        const cur = cite ? answerCites.findIndex((c) => c.n === cite.c.n && c.chunk_id === cite.c.chunk_id) : -1;
        const next = e.key === "j" ? (cur + 1) % answerCites.length : (cur - 1 + answerCites.length) % answerCites.length;
        jump(answerCites[next]);
      } else if (e.key === "h" && sel) void addNote("yellow");
      else if (e.key === "n" && sel) void addNote("blue", window.prompt("Note") ?? "");
      else if (e.key === "g") lastG = Date.now();
      else if (e.key === "s" && Date.now() - lastG < 800) {
        setPanelOpen(true);
        setTab("summary");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [answerCites, cite, sel, addNote, jump]);

  if (ready && paper.isError) return <div className="p-6"><ErrorState error={paper.error} onRetry={() => void paper.refetch()} /></div>;
  const p = paper.data;
  const title = p?.title ?? p?.source_ref ?? "Untitled paper";

  const panel = p && (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <Tabs
        className="border-b border-line px-2 py-1.5"
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "chat", label: "Chat" },
          { value: "summary", label: "Summary" },
          { value: "notes", label: `Notes${notes.data?.length ? ` (${notes.data.length})` : ""}` },
          { value: "glossary", label: "Glossary" },
          { value: "refs", label: "References" },
          { value: "cards", label: "Cards" },
        ]}
      />
      <div className="min-h-0 flex-1 overflow-auto">
        <div className={cn("h-full", tab !== "chat" && "hidden")}>
          <ChatPanel
            userId={userId}
            paperId={id}
            paperTitle={title}
            collectionId={p.collection_id}
            onCite={jump}
            registerAsk={(fn) => (askRef.current = fn)}
            onCitationsChange={setAnswerCites}
          />
        </div>
        {tab === "summary" && <SummaryPanel userId={userId} paper={p} onCite={jump} />}
        {tab === "notes" && <NotesPanel userId={userId} paper={p} notes={notes.data ?? []} onJump={(n) => n.anchor && viewer.current?.scrollTo(n.anchor.page, n.anchor.rects[0] as Highlight["rect"])} />}
        {tab === "glossary" && <GlossaryPanel userId={userId} paper={p} onCite={jump} />}
        {tab === "refs" && <ReferencesPanel userId={userId} paper={p} />}
        {tab === "cards" && <CardsPanel userId={userId} paper={p} onCite={jump} />}
      </div>
    </div>
  );

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-surface px-2">
        <Link href="/library" className="flex h-9 items-center gap-1 rounded-lg px-2 text-sm text-muted-foreground hover:text-ink" aria-label="Back to library">
          <ArrowLeft className="size-4" aria-hidden /> <span className="hidden sm:inline">Library</span>
        </Link>
        <div className="min-w-0 flex-1 truncate text-sm">
          <span className="font-semibold">{title}</span>
          {p && <span className="text-muted-foreground"> · {p.authors[0]?.name ?? ""}{p.authors.length > 1 ? " et al." : ""} {p.year ?? ""}</span>}
        </div>
        {p && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={p.starred ? "Unstar" : "Star"}
            onClick={async () => {
              await api.updatePaper(id, { starred: !p.starred });
              void qc.invalidateQueries({ queryKey: queryKeys.paper(userId, id) });
            }}
          >
            <Star className={cn("size-4", p.starred && "fill-warn text-warn")} aria-hidden />
          </Button>
        )}
        <Link href={`/paper/${id}/debug`} className="hidden h-9 items-center rounded-lg px-2 text-muted-foreground hover:text-ink lg:flex" aria-label="Parser debug view" title="Parser debug view">
          <Bug className="size-4" aria-hidden />
        </Link>
        <ThemeToggle />
        <Button variant="ghost" size="icon" className="hidden lg:inline-flex" aria-label={panelOpen ? "Hide panel" : "Show panel"} onClick={() => setPanelOpen((o) => !o)}>
          {panelOpen ? <PanelRightClose aria-hidden /> : <PanelRightOpen aria-hidden />}
        </Button>
      </header>

      {!p || (p.status === "ready" && file.isPending) ? (
        <div className="flex flex-1 gap-4 p-4"><Skeleton className="h-full flex-1" /><Skeleton className="hidden h-full w-96 lg:block" /></div>
      ) : p.status !== "ready" ? (
        <div className="mx-auto mt-16 max-w-md p-4 text-center">
          {p.status === "failed" ? (
            <ErrorState error={new Error(p.error ?? "Indexing failed.")} title="This paper couldn't be indexed" />
          ) : (
            <p className="flex items-center justify-center gap-2 text-muted-foreground"><Loader2 className="animate-spin" aria-hidden /> Indexing… ({p.status})</p>
          )}
        </div>
      ) : file.isError ? (
        <div className="p-6"><ErrorState error={file.error} onRetry={() => void file.refetch()} /></div>
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* Outline */}
          {outline && (
            <nav aria-label="Outline" className="hidden w-56 shrink-0 overflow-auto border-r border-line bg-surface p-2 text-sm xl:block">
              <p className="px-2 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Outline</p>
              {p.sections.filter((s) => s.heading !== "Front matter").map((s) => (
                <button
                  key={s.id}
                  onClick={() => s.page_start && viewer.current?.scrollTo(s.page_start)}
                  className={cn("block w-full truncate rounded px-2 py-1 text-left hover:bg-brand-soft", s.level > 1 && "pl-5 text-muted-foreground", s.level > 2 && "pl-8")}
                  title={s.heading}
                >
                  {s.heading}
                </button>
              ))}
            </nav>
          )}

          {/* Paper */}
          <section className={cn("relative min-w-0 flex-1 flex-col", mobile === "paper" ? "flex" : "hidden lg:flex")}>
            <div className="flex h-10 shrink-0 items-center gap-1 border-b border-line bg-surface px-2 text-xs">
              <Button size="icon-sm" variant="ghost" className="hidden xl:inline-flex" aria-label="Toggle outline" onClick={() => setOutline((o) => !o)}>
                <ListTree aria-hidden />
              </Button>
              <Button size="icon-sm" variant="ghost" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.15).toFixed(2)))}><Minus aria-hidden /></Button>
              <span className="w-10 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
              <Button size="icon-sm" variant="ghost" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(3, +(z + 0.15).toFixed(2)))}><Plus aria-hidden /></Button>
              <span className="ml-2 tabular-nums text-muted-foreground">p. {page.n} / {page.of || "…"}</span>
              <form
                className="ml-auto flex items-center gap-1"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const hits = (await viewer.current?.find(find)) ?? [];
                  setFindHits(hits);
                  if (hits[0]) viewer.current?.scrollTo(hits[0]);
                }}
              >
                <Search className="size-3.5 text-muted-foreground" aria-hidden />
                <Input aria-label="Find in paper" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find in paper" className="h-7 w-32 text-xs sm:w-44" />
              </form>
            </div>
            {findHits && (
              <div className="flex flex-wrap items-center gap-1 border-b border-line bg-brand-soft/50 px-2 py-1 text-xs">
                {findHits.length ? <>Found on pages: {findHits.map((h) => <button key={h} className="rounded px-1 underline" onClick={() => viewer.current?.scrollTo(h)}>{h}</button>)}</> : "No matches."}
                <button className="ml-auto" aria-label="Close search results" onClick={() => setFindHits(null)}><X className="size-3" /></button>
              </div>
            )}
            <div className="min-h-0 flex-1">
              {file.data && (
                <PdfViewer
                  ref={viewer}
                  data={file.data}
                  zoom={zoom}
                  highlights={highlights}
                  onSelection={setSel}
                  onPage={onPage}
                  onLoaded={fitMobile}
                />
              )}
            </div>
            {sel && <SelectionToolbar sel={sel} onClose={() => setSel(null)} onHighlight={() => void addNote("yellow")}
              onNote={() => void addNote("blue", window.prompt("Note for this passage") ?? "")} onExplain={runExplain}
              onAsk={() => { const s = sel; setSel(null); setPanelOpen(true); setTab("chat"); setMobile("ask"); askRef.current?.(window.prompt("Ask about this passage") || "Explain this passage", { page: s.page, text: s.text }); }} />}
            {explain && <ExplainCard e={explain} onClose={() => setExplain(null)} onCite={jump} onSave={async () => {
              await api.createNote(id, { anchor: { page: explain.page, rects: [], text: explain.text }, body_md: explain.out, color: "purple" });
              void qc.invalidateQueries({ queryKey: queryKeys.notes(userId, id) });
              setExplain(null);
            }} />}
          </section>

          {/* Resizable panel (desktop) */}
          {panelOpen && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize panel"
              tabIndex={0}
              className="hidden w-1.5 shrink-0 cursor-col-resize bg-line hover:bg-brand/40 lg:block"
              onPointerDown={(e) => {
                const startX = e.clientX;
                const startW = panelW;
                const move = (ev: PointerEvent) => setPanelW(Math.min(900, Math.max(360, startW - (ev.clientX - startX))));
                const up = () => {
                  window.removeEventListener("pointermove", move);
                  window.removeEventListener("pointerup", up);
                  setPanelW((w) => {
                    try { localStorage.setItem("paperly.panelW", String(w)); } catch { /* ignore */ }
                    return w;
                  });
                };
                window.addEventListener("pointermove", move);
                window.addEventListener("pointerup", up);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") setPanelW((w) => Math.min(900, w + 24));
                if (e.key === "ArrowRight") setPanelW((w) => Math.max(360, w - 24));
              }}
            />
          )}
          <aside
            aria-label="AI panel"
            className={cn("min-h-0 shrink-0 border-l border-line", panelOpen ? "lg:block" : "lg:hidden", mobile === "paper" ? "hidden" : "block w-full lg:w-auto")}
            style={{ width: undefined, flexBasis: undefined }}
          >
            <div className="h-full lg:w-[var(--pw)]" style={{ ["--pw" as string]: `${panelW}px` }}>
              {mobile === "notes" ? (
                <div className="h-full overflow-auto lg:hidden">{p && <NotesPanel userId={userId} paper={p} notes={notes.data ?? []} onJump={(n) => { setMobile("paper"); setTimeout(() => n.anchor && viewer.current?.scrollTo(n.anchor.page), 50); }} />}</div>
              ) : null}
              <div className={cn("h-full", mobile === "notes" && "hidden lg:block")}>{panel}</div>
            </div>
          </aside>
        </div>
      )}

      {/* Mobile tabs */}
      <nav aria-label="Reader" className="grid h-14 shrink-0 grid-cols-3 border-t border-line bg-surface lg:hidden">
        {([["paper", "Paper", FileText], ["ask", "Ask", MessageSquare], ["notes", "Notes", NotebookPen]] as const).map(([v, label, Icon]) => (
          <button key={v} onClick={() => setMobile(v)} className={cn("flex flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground", mobile === v && "text-brand")}>
            <Icon className="size-5" aria-hidden /> {label}
          </button>
        ))}
      </nav>
    </div>
  );
}

function SelectionToolbar({
  sel,
  onClose,
  onHighlight,
  onNote,
  onExplain,
  onAsk,
}: {
  sel: SelectionInfo;
  onClose: () => void;
  onHighlight: () => void;
  onNote: () => void;
  onExplain: (k: Explain["kind"]) => void;
  onAsk: () => void;
}) {
  const looksMath = /[=∑∫√≤≥±×·∂αβγδθλμσφψω^_]/.test(sel.text) && sel.text.length < 400;
  const btn = "flex h-9 items-center gap-1.5 rounded-md px-2 text-xs font-medium hover:bg-brand-soft";
  return (
    <div
      role="toolbar"
      aria-label="Selection actions"
      className="fixed z-40 flex -translate-x-1/2 -translate-y-full flex-wrap items-center gap-0.5 rounded-xl border border-line bg-surface p-1 shadow-xl"
      style={{ left: Math.min(Math.max(sel.clientX, 180), window.innerWidth - 180), top: Math.max(sel.clientY - 8, 64) }}
      onMouseUp={(e) => e.stopPropagation()}
    >
      <button className={btn} onClick={onHighlight}><Highlighter className="size-3.5" aria-hidden /> Highlight</button>
      <button className={btn} onClick={onNote}><NotebookPen className="size-3.5" aria-hidden /> Note</button>
      <button className={btn} onClick={() => onExplain(looksMath ? "equation" : "explain")}>
        {looksMath ? <Sigma className="size-3.5" aria-hidden /> : <Lightbulb className="size-3.5" aria-hidden />} Explain
      </button>
      <button className={btn} onClick={() => onExplain("simplify")}><Sparkles className="size-3.5" aria-hidden /> Simplify</button>
      <button className={btn} onClick={() => onExplain("translate")}><Languages className="size-3.5" aria-hidden /> Translate</button>
      <button className={btn} onClick={onAsk}><MessageSquare className="size-3.5" aria-hidden /> Ask</button>
      <button className="flex size-9 items-center justify-center rounded-md hover:bg-brand-soft" aria-label="Close" onClick={onClose}><X className="size-3.5" /></button>
    </div>
  );
}

function ExplainCard({ e, onClose, onCite, onSave }: { e: Explain; onClose: () => void; onCite: (c: Citation) => void; onSave: () => void }) {
  return (
    <div role="dialog" aria-label={`${e.kind} result`} className="absolute bottom-3 left-1/2 z-40 max-h-[55%] w-[min(640px,calc(100%-24px))] -translate-x-1/2 overflow-auto rounded-2xl border border-line bg-surface p-4 shadow-2xl">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{e.kind} · p.{e.page}</span>
        <span className="ml-auto" />
        {!e.busy && e.out && <Button size="sm" variant="ghost" onClick={onSave}><NotebookPen aria-hidden /> Save note</Button>}
        <Button size="icon-sm" variant="ghost" aria-label="Close" onClick={onClose}><X aria-hidden /></Button>
      </div>
      <blockquote className="mb-2 line-clamp-3 border-l-2 border-line pl-2 text-xs text-muted-foreground">{e.text}</blockquote>
      {e.error ? <p className="text-sm text-danger">{e.error}</p> : e.out ? (
        <Markdown text={e.out} citations={e.cites} onCite={onCite} streaming={e.busy} className="font-serif text-[15px]" />
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden /> Thinking…</p>
      )}
    </div>
  );
}
