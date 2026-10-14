"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Loader2, NotebookPen, Plus, Send, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { GroundingBadge, selectClass } from "@/components/bits";
import { Markdown, paperHue } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { ApiError, api, queryKeys } from "@/lib/api";
import { streamSse } from "@/lib/sse";
import type { Citation, Level, Message, Thread } from "@/lib/types";
import { cn } from "@/lib/utils";

export const LANGS: [string, string][] = [
  ["en", "English"], ["es", "Español"], ["fr", "Français"], ["de", "Deutsch"], ["pt", "Português"],
  ["zh", "中文"], ["ja", "日本語"], ["hi", "हिन्दी"], ["ur", "اردو"], ["ar", "العربية"], ["auto", "Auto-detect"],
];

type Scope = { kind: "paper" } | { kind: "papers"; ids: string[] } | { kind: "collection"; id: string };

export type ChatHandle = { ask: (q: string, selection?: { page: number; text: string }) => void };

export function ChatPanel({
  userId,
  paperId,
  paperTitle,
  collectionId,
  onCite,
  registerAsk,
  onCitationsChange,
}: {
  userId: string;
  paperId: string;
  paperTitle: string;
  collectionId: string | null;
  onCite: (c: Citation) => void;
  registerAsk?: (fn: ChatHandle["ask"]) => void;
  onCitationsChange?: (c: Citation[]) => void;
}) {
  const qc = useQueryClient();
  const [scope, setScope] = useState<Scope>({ kind: "paper" });
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [level, setLevel] = useState<Level>("student");
  const [lang, setLang] = useState("en");
  const [strict, setStrict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const threads = useQuery({
    queryKey: queryKeys.threads(userId, paperId),
    queryFn: () => api.threads(paperId),
    enabled: !!userId,
  });
  const papers = useQuery({ queryKey: queryKeys.papers(userId), queryFn: () => api.papers(), enabled: scope.kind === "papers" });

  // Open the latest single-paper thread for this paper.
  useEffect(() => {
    if (threadId || !threads.data) return;
    const t = threads.data.find((x) => x.scope.paper_ids?.length === 1 && x.scope.paper_ids[0] === paperId);
    if (!t) return;
    let alive = true;
    void api.thread(t.id).then((d) => {
      if (!alive) return;
      setThreadId(t.id);
      setMessages(d.messages);
    });
    return () => {
      alive = false;
    };
  }, [threads.data, threadId, paperId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  const last = [...messages].reverse().find((m) => m.role === "assistant");
  useEffect(() => {
    onCitationsChange?.(last?.citations ?? []);
  }, [last, onCitationsChange]);

  async function ensureThread(): Promise<string> {
    if (threadId) return threadId;
    const s: Thread["scope"] =
      scope.kind === "paper"
        ? { paper_ids: [paperId] }
        : scope.kind === "papers"
          ? { paper_ids: [paperId, ...scope.ids.filter((x) => x !== paperId)] }
          : { collection_id: scope.id };
    const t = await api.createThread(s);
    setThreadId(t.id);
    void qc.invalidateQueries({ queryKey: ["threads"] });
    return t.id;
  }

  const ask = useCallback(
    async (q: string, selection?: { page: number; text: string }) => {
      const content = q.trim();
      if (!content || busy) return;
      setBusy(true);
      setInput("");
      const now = new Date().toISOString();
      const userMsg: Message = { id: `u${now}`, role: "user", content, citations: [], grounded: null, support_score: null,
        provider: null, model: null, latency_ms: null, created_at: now };  // prettier-ignore
      const draft: Message = { id: "draft", role: "assistant", content: "", citations: [], grounded: null,
        support_score: null, provider: null, model: null, latency_ms: null, created_at: now };  // prettier-ignore
      setMessages((m) => [...m, userMsg, draft]);
      const update = (fn: (m: Message) => Message) => setMessages((ms) => ms.map((x) => (x.id === "draft" ? fn(x) : x)));
      abort.current = new AbortController();
      try {
        const tid = await ensureThread();
        const body = { content, mode: strict ? "strict" : "grounded", level, lang,
          selection: selection ? { paper_id: paperId, page: selection.page, text: selection.text } : null };  // prettier-ignore
        for await (const ev of streamSse(`/v1/threads/${tid}/messages`, { method: "POST", body: JSON.stringify(body) }, abort.current.signal)) {
          const d = ev.data;
          if (ev.event === "token") update((m) => ({ ...m, content: m.content + String(d.t) }));
          else if (ev.event === "citation") update((m) => ({ ...m, citations: [...m.citations, d as unknown as Citation] }));
          else if (ev.event === "meta" && d.provider === "extractive")
            setToast("No AI model configured — showing the most relevant passages.");
          else if (ev.event === "diagram") update((m) => ({ ...m, diagram: String(d.mermaid) }));
          else if (ev.event === "done") {
            update((m) => ({
              ...m,
              id: String(d.message_id),
              grounded: (d.grounded as boolean | null) ?? null,
              support_score: (d.support_score as number | null) ?? null,
              provider: (d.provider as string) ?? null,
              model: (d.model as string) ?? null,
              latency_ms: (d.latency_ms as number) ?? null,
              not_found: Boolean(d.not_found),
              closest: (d.closest as Message["closest"]) ?? undefined,
              content: d.not_found && !m.content ? "" : m.content,
            }));
            if (d.provider && d.provider !== "groq" && d.provider !== "extractive" && !d.cached)
              setToast(`Answered by backup model (${String(d.provider)}).`);
          } else if (ev.event === "error") {
            update((m) => ({ ...m, id: `e${Date.now()}`, content: `⚠️ ${String(d.message)}`, not_found: false }));
          }
        }
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          const msg = e instanceof ApiError ? e.message : "Something went wrong. Try again.";
          update((m) => ({ ...m, id: `e${Date.now()}`, content: `⚠️ ${msg}` }));
        } else update((m) => ({ ...m, id: `s${Date.now()}` }));
      } finally {
        setBusy(false);
        void qc.invalidateQueries({ queryKey: ["usage"] });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ensureThread reads the latest state
    [busy, level, lang, strict, paperId, threadId, scope],
  );

  useEffect(() => {
    registerAsk?.((q, sel) => void ask(q, sel));
  }, [ask, registerAsk]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(t.tagName)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const scopeIds = scope.kind === "papers" ? [paperId, ...scope.ids] : [paperId];
  const hue = scope.kind === "paper" ? undefined : (c: Citation) => paperHue(c.paper_id, scopeIds);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2 text-xs">
        <label className="sr-only" htmlFor="scope">Scope</label>
        <select
          id="scope"
          className={selectClass}
          value={scope.kind === "collection" ? "collection" : scope.kind}
          onChange={(e) => {
            const v = e.target.value;
            setThreadId(null);
            setMessages([]);
            if (v === "paper") setScope({ kind: "paper" });
            else if (v === "papers") setScope({ kind: "papers", ids: [] });
            else if (collectionId) setScope({ kind: "collection", id: collectionId });
          }}
        >
          <option value="paper">This paper</option>
          <option value="papers">Selected papers</option>
          {collectionId && <option value="collection">Its collection</option>}
        </select>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            abort.current?.abort();
            setThreadId(null);
            setMessages([]);
          }}
        >
          <Plus aria-hidden /> New chat
        </Button>
      </div>
      {scope.kind === "papers" && (
        <div className="flex max-h-28 flex-wrap gap-1 overflow-auto border-b border-line px-3 py-2">
          {papers.data?.items
            .filter((p) => p.id !== paperId && p.status === "ready")
            .map((p) => {
              const on = scope.ids.includes(p.id);
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    setThreadId(null);
                    setMessages([]);
                    setScope({ kind: "papers", ids: on ? scope.ids.filter((x) => x !== p.id) : [...scope.ids, p.id] });
                  }}
                  className={cn("max-w-56 truncate rounded-full border px-2 py-0.5 text-xs", on ? "border-brand bg-brand-soft" : "border-line")}
                >
                  {p.title ?? "Untitled"}
                </button>
              );
            })}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto px-3 py-4" aria-live="polite">
        {messages.length === 0 && (
          <div className="flex flex-col gap-2 text-sm text-muted-foreground">
            <p>Ask anything about <em>{paperTitle}</em>. Every claim links to the exact sentence.</p>
            {["What problem does this paper solve?", "Explain the method step by step", "What are the main results?", "What are the limitations?"].map((s) => (
              <button key={s} onClick={() => void ask(s)} className="w-fit rounded-full border border-line px-3 py-1 text-left text-xs hover:border-brand">
                {s}
              </button>
            ))}
          </div>
        )}
        <ul className="flex flex-col gap-4">
          {messages.map((m) => (
            <MessageView key={m.id} m={m} paperId={paperId} onCite={onCite} hue={hue} streaming={busy && m.id === "draft"} />
          ))}
        </ul>
        <div ref={bottom} />
      </div>

      {toast && <div role="status" className="mx-3 mb-2 rounded-lg bg-brand-soft px-3 py-2 text-xs">{toast}</div>}

      <form
        className="border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
          <select aria-label="Explanation level" className={selectClass} value={level} onChange={(e) => setLevel(e.target.value as Level)}>
            <option value="eli5">ELI5</option>
            <option value="student">Student</option>
            <option value="expert">Expert</option>
          </select>
          <select aria-label="Answer language" className={selectClass} value={lang} onChange={(e) => setLang(e.target.value)}>
            {LANGS.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
          <label className="flex items-center gap-1.5 text-muted-foreground">
            <input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} /> Strict
          </label>
        </div>
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void ask(input);
              }
            }}
            placeholder="Ask about this paper…  ( / to focus )"
            aria-label="Ask a question"
            className="min-h-11 flex-1 resize-none rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          {busy ? (
            <Button type="button" size="icon-lg" variant="outline" aria-label="Stop" onClick={() => abort.current?.abort()}>
              <Square aria-hidden />
            </Button>
          ) : (
            <Button type="submit" size="icon-lg" aria-label="Send" disabled={!input.trim()}>
              <Send aria-hidden />
            </Button>
          )}
        </div>
      </form>
    </div>
  );
}

function MessageView({
  m,
  paperId,
  onCite,
  hue,
  streaming,
}: {
  m: Message;
  paperId: string;
  onCite: (c: Citation) => void;
  hue?: (c: Citation) => string;
  streaming: boolean;
}) {
  const [rated, setRated] = useState<1 | -1 | null>(null);
  const [saved, setSaved] = useState(false);
  if (m.role === "user")
    return (
      <li className="ml-8 self-end rounded-2xl rounded-br-sm bg-brand-soft px-3 py-2 text-sm" dir="auto">
        {m.content}
      </li>
    );
  const persisted = !/^(draft|e|s)/.test(m.id) || /^[0-9a-f-]{36}$/.test(m.id);
  return (
    <li className="flex flex-col gap-2">
      {m.content ? (
        <Markdown text={m.content} citations={m.citations} onCite={onCite} hue={hue} streaming={streaming} className="font-serif text-[15px]" />
      ) : streaming ? (
        <span className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" aria-hidden /> Reading the paper…</span>
      ) : null}
      {m.not_found && (
        <div className="rounded-lg border border-line p-3 text-sm">
          <p className="font-medium">Not found in these papers.</p>
          <p className="text-muted-foreground">Try asking about the method or results, or widen the scope.</p>
          {!!m.closest?.length && (
            <>
              <p className="mt-2 text-xs font-medium text-muted-foreground">You might be looking for…</p>
              <ul className="mt-1 flex flex-col gap-1">
                {m.closest.map((c) => (
                  <li key={c.chunk_id}>
                    <button
                      className="text-left text-xs hover:text-brand"
                      onClick={() => onCite({ n: 0, paper_id: c.paper_id, chunk_id: c.chunk_id, page: c.page, section: c.section, sentence_idx: [], quote: c.quote, rects: [] })}
                    >
                      p.{c.page} · {c.section ?? ""} — “{c.quote.slice(0, 120)}…”
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      {!streaming && m.citations.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground">Sources ({m.citations.length})</summary>
          <ol className="mt-1 flex flex-col gap-1">
            {m.citations.map((c) => (
              <li key={c.n}>
                <button className="text-left hover:text-brand" onClick={() => onCite(c)}>
                  <span className="font-semibold">[{c.n}]</span> {c.paper_title ? `${c.paper_title} · ` : ""}
                  {c.section ?? ""} · p.{c.page} — <span className="text-muted-foreground">“{c.quote.slice(0, 140)}”</span>
                </button>
              </li>
            ))}
          </ol>
        </details>
      )}
      {!streaming && persisted && m.content && (
        <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          <GroundingBadge grounded={m.grounded} score={m.support_score} notFound={m.not_found} />
          {m.provider && <span className="ml-1">{m.provider === "extractive" ? "extractive" : m.provider}</span>}
          <span className="ml-auto" />
          <Button size="icon-sm" variant="ghost" aria-label="Copy answer" onClick={() => void navigator.clipboard.writeText(m.content)}>
            <Copy aria-hidden />
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Save to notes"
            disabled={saved}
            onClick={async () => {
              await api.saveNote(m.id, paperId);
              setSaved(true);
            }}
          >
            <NotebookPen aria-hidden className={saved ? "text-ok" : ""} />
          </Button>
          {([1, -1] as const).map((r) => (
            <Button
              key={r}
              size="icon-sm"
              variant="ghost"
              aria-label={r === 1 ? "Helpful" : "Not helpful"}
              aria-pressed={rated === r}
              onClick={async () => {
                setRated(r);
                await api.feedback(m.id, r).catch(() => undefined);
              }}
            >
              {r === 1 ? <ThumbsUp aria-hidden className={rated === 1 ? "text-ok" : ""} /> : <ThumbsDown aria-hidden className={rated === -1 ? "text-danger" : ""} />}
            </Button>
          ))}
        </div>
      )}
    </li>
  );
}
