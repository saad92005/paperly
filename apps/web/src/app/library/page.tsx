"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, FolderPlus, Link2, MoreHorizontal, Plus, Search, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { Empty, ErrorState, Skeleton, StatusPill, selectClass } from "@/components/bits";
import { ImportDialog } from "@/components/import-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, kickWorker, queryKeys } from "@/lib/api";
import type { PaperCard } from "@/lib/types";
import { cn } from "@/lib/utils";

type View = { kind: "all" } | { kind: "starred" } | { kind: "collection"; id: string };

export default function LibraryPage() {
  const { userId, ready } = useRequireUser();
  const qc = useQueryClient();
  const [view, setView] = useState<View>({ kind: "all" });
  const [q, setQ] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const filters = {
    q: q.trim() || undefined,
    starred: view.kind === "starred" ? true : undefined,
    collection_id: view.kind === "collection" ? view.id : undefined,
  };
  const papers = useQuery({
    queryKey: queryKeys.papers(userId, filters),
    queryFn: () => api.papers(filters),
    enabled: ready,
    // Poll while anything is still being indexed (live status without a socket).
    refetchInterval: (query) => {
      const pending = query.state.data?.items.some((p) => p.status !== "ready" && p.status !== "failed");
      if (pending) kickWorker();
      return pending ? 2000 : false;
    },
  });
  const collections = useQuery({ queryKey: queryKeys.collections(userId), queryFn: api.collections, enabled: ready });
  const newCollection = useMutation({
    mutationFn: (name: string) => api.createCollection(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["collections"] }),
  });

  const items = papers.data?.items ?? [];
  const isEmptyLibrary = view.kind === "all" && !q && items.length === 0;

  return (
    <AppShell>
      <div className="flex flex-col gap-6 lg:flex-row">
        <aside className="flex shrink-0 flex-row gap-1 overflow-x-auto lg:w-48 lg:flex-col" aria-label="Library views">
          <SideItem active={view.kind === "all"} onClick={() => setView({ kind: "all" })}>
            All papers
          </SideItem>
          <SideItem active={view.kind === "starred"} onClick={() => setView({ kind: "starred" })}>
            Starred
          </SideItem>
          <p className="mt-3 hidden px-3 text-xs font-medium uppercase tracking-wide text-muted-foreground lg:block">
            Collections
          </p>
          {collections.data?.map((c) => (
            <SideItem
              key={c.id}
              active={view.kind === "collection" && view.id === c.id}
              onClick={() => setView({ kind: "collection", id: c.id })}
            >
              <span className="truncate">{c.name}</span>
              <span className="ml-auto text-xs text-muted-foreground">{c.paper_count}</span>
            </SideItem>
          ))}
          <SideItem
            onClick={() => {
              const name = window.prompt("Collection name");
              if (name?.trim()) newCollection.mutate(name.trim());
            }}
          >
            <FolderPlus className="size-4" aria-hidden /> New collection
          </SideItem>
        </aside>

        <section className="min-w-0 flex-1">
          <PageTitle
            title={
              view.kind === "collection"
                ? (collections.data?.find((c) => c.id === view.id)?.name ?? "Collection")
                : view.kind === "starred"
                  ? "Starred"
                  : "Your library"
            }
            sub={papers.data ? `${items.length} paper${items.length === 1 ? "" : "s"}` : undefined}
          >
            {view.kind === "collection" && (
              <CollectionActions id={view.id} onDeleted={() => setView({ kind: "all" })} />
            )}
            <Button className="h-10" onClick={() => setImportOpen(true)}>
              <Plus aria-hidden /> Add papers
            </Button>
          </PageTitle>

          {!isEmptyLibrary && (
            <div className="relative mb-4">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                aria-label="Search your library"
                placeholder="Search titles, authors, abstracts, tags…"
                className="h-10 pl-9"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
          )}

          {!ready || papers.isPending ? (
            <div className="grid gap-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24 rounded-xl" />
              ))}
            </div>
          ) : papers.isError ? (
            <ErrorState error={papers.error} onRetry={() => void papers.refetch()} title="We couldn't load your library" />
          ) : isEmptyLibrary ? (
            <EmptyLibrary onImport={() => setImportOpen(true)} />
          ) : items.length === 0 ? (
            <Empty title="Nothing here yet">
              {q ? "No papers match your search." : "Add papers to this view from the library or the import dialog."}
            </Empty>
          ) : (
            <ul className="grid gap-3">
              {items.map((p) => (
                <PaperRow key={p.id} p={p} collections={collections.data ?? []} />
              ))}
            </ul>
          )}
        </section>
      </div>
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        collectionId={view.kind === "collection" ? view.id : null}
      />
    </AppShell>
  );
}

function SideItem({ children, active, onClick }: { children: React.ReactNode; active?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-left text-sm text-muted-foreground hover:bg-brand-soft hover:text-ink",
        active && "bg-brand-soft font-medium text-ink",
      )}
    >
      {children}
    </button>
  );
}

function CollectionActions({ id, onDeleted }: { id: string; onDeleted: () => void }) {
  const qc = useQueryClient();
  return (
    <>
      <Link href={`/reviews?collection=${id}`} className={cn(buttonVariants({ variant: "outline" }), "h-10")}>
        Draft lit review
      </Link>
      <Button
        variant="ghost"
        className="h-10"
        aria-label="Delete collection"
        onClick={async () => {
          if (!window.confirm("Delete this collection? Papers stay in your library.")) return;
          await api.deleteCollection(id);
          await qc.invalidateQueries({ queryKey: ["collections"] });
          onDeleted();
        }}
      >
        <Trash2 aria-hidden />
      </Button>
    </>
  );
}

const IMPORT_TILES = [
  { icon: FileUp, title: "Upload PDFs", body: "Drag and drop text-based PDFs up to 25 MB." },
  { icon: Link2, title: "arXiv or DOI", body: "Paste an ID like 1706.03762 or a DOI." },
  { icon: Search, title: "Search papers", body: "Find open-access papers on arXiv and Semantic Scholar." },
];

function EmptyLibrary({ onImport }: { onImport: () => void }) {
  const qc = useQueryClient();
  const demo = useMutation({
    mutationFn: () => api.importPaper("arxiv", "1706.03762"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["papers"] }),
  });
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="Add papers" className="grid gap-4 sm:grid-cols-3">
        {IMPORT_TILES.map(({ icon: Icon, title, body }) => (
          <button
            key={title}
            onClick={onImport}
            className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-5 text-left transition hover:border-brand"
          >
            <Icon className="size-5 text-brand" aria-hidden />
            <h2 className="font-semibold">{title}</h2>
            <p className="text-sm text-muted-foreground">{body}</p>
          </button>
        ))}
      </section>
      <p className="text-sm text-muted-foreground">
        Try with a classic:{" "}
        <button className="font-medium text-brand underline-offset-2 hover:underline" onClick={() => demo.mutate()}>
          {demo.isPending ? "Importing…" : <em>Attention Is All You Need</em>}
        </button>
        {demo.isError && <span className="ml-2 text-danger">{(demo.error as Error).message}</span>}
      </p>
    </div>
  );
}

function PaperRow({ p, collections }: { p: PaperCard; collections: { id: string; name: string }[] }) {
  const qc = useQueryClient();
  const [menu, setMenu] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: ["papers"] });
  const star = useMutation({ mutationFn: () => api.updatePaper(p.id, { starred: !p.starred }), onSuccess: refresh });
  const ready = p.status === "ready";
  const title = p.title ?? p.source_ref ?? "Untitled paper";
  const authors = p.authors.map((a) => a.name);

  return (
    <li className="relative flex gap-3 rounded-xl border border-line bg-surface p-4 transition hover:border-brand/60">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {ready ? (
            <Link href={`/paper/${p.id}`} className="font-semibold leading-snug after:absolute after:inset-0 hover:text-brand">
              {title}
            </Link>
          ) : (
            <span className="font-semibold leading-snug">{title}</span>
          )}
          <StatusPill status={p.status} />
        </div>
        <p className="mt-1 truncate text-sm text-muted-foreground">
          {authors.slice(0, 3).join(", ")}
          {authors.length > 3 && " et al."}
          {(p.year || p.venue) && " · "}
          {p.year}
          {p.venue ? ` · ${p.venue}` : ""}
          {p.page_count ? ` · ${p.page_count} pages` : ""}
        </p>
        {p.status === "failed" && p.error && <p className="mt-1 text-sm text-danger">{p.error}</p>}
        {ready && p.read_progress > 0 && (
          <div className="mt-2 h-1 w-40 overflow-hidden rounded-full bg-muted" aria-label={`Read ${Math.round(p.read_progress * 100)}%`}>
            <div className="h-full bg-brand" style={{ width: `${Math.round(p.read_progress * 100)}%` }} />
          </div>
        )}
      </div>
      <div className="relative z-10 flex shrink-0 items-start gap-1">
        <Button variant="ghost" size="icon" aria-label={p.starred ? "Unstar" : "Star"} onClick={() => star.mutate()}>
          <Star className={cn("size-4", p.starred && "fill-warn text-warn")} aria-hidden />
        </Button>
        <Button variant="ghost" size="icon" aria-label="More actions" onClick={() => setMenu((m) => !m)}>
          <MoreHorizontal aria-hidden />
        </Button>
        {menu && (
          <div className="absolute right-0 top-10 z-20 flex w-56 flex-col gap-2 rounded-xl border border-line bg-surface p-3 shadow-xl">
            <label className="text-xs text-muted-foreground" htmlFor={`col-${p.id}`}>
              Collection
            </label>
            <select
              id={`col-${p.id}`}
              className={selectClass}
              value={p.collection_id ?? ""}
              onChange={async (e) => {
                await api.updatePaper(p.id, { collection_id: e.target.value || null });
                refresh();
                void qc.invalidateQueries({ queryKey: ["collections"] });
                setMenu(false);
              }}
            >
              <option value="">None</option>
              {collections.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <Button
              variant="ghost"
              className="justify-start text-danger"
              onClick={async () => {
                if (!window.confirm("Remove this paper from your library?")) return;
                await api.deletePaper(p.id);
                refresh();
              }}
            >
              <Trash2 aria-hidden /> Remove
            </Button>
          </div>
        )}
      </div>
    </li>
  );
}
