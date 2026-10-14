"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, Plus, Search } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Dialog, Tabs } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import type { DiscoverResult } from "@/lib/types";

type Tab = "upload" | "id" | "search";

function detect(value: string): { source: "arxiv" | "doi" | "url"; label: string } | null {
  const v = value.trim();
  if (!v) return null;
  if (/^(https?:\/\/)?(www\.)?arxiv\.org\//i.test(v) || /^(arxiv:)?\d{4}\.\d{4,5}(v\d+)?$/i.test(v))
    return { source: "arxiv", label: "arXiv paper" };
  if (/^(https?:\/\/)?(dx\.)?doi\.org\/10\./i.test(v) || /^(doi:\s*)?10\.\d{4,9}\//i.test(v))
    return { source: "doi", label: "DOI (open-access PDF)" };
  if (/^https?:\/\/\S+$/i.test(v)) return { source: "url", label: "PDF link" };
  return null;
}

export function ImportDialog({
  open,
  onClose,
  collectionId,
}: {
  open: boolean;
  onClose: () => void;
  collectionId?: string | null;
}) {
  const [tab, setTab] = useState<Tab>("upload");
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["papers"] });

  return (
    <Dialog open={open} onClose={onClose} title="Add papers" wide>
      <Tabs
        tabs={[
          { value: "upload", label: "Upload PDF" },
          { value: "id", label: "arXiv / DOI / link" },
          { value: "search", label: "Search" },
        ]}
        value={tab}
        onChange={setTab}
        className="mb-4"
      />
      {tab === "upload" && <UploadTab collectionId={collectionId} onDone={() => (refresh(), onClose())} />}
      {tab === "id" && <IdTab collectionId={collectionId} onDone={() => (refresh(), onClose())} />}
      {tab === "search" && <SearchTab collectionId={collectionId} onAdded={refresh} />}
    </Dialog>
  );
}

function UploadTab({ collectionId, onDone }: { collectionId?: string | null; onDone: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);

  function pick(list: FileList | null) {
    if (!list) return;
    setFiles((f) => [...f, ...Array.from(list).filter((x) => x.type === "application/pdf" || x.name.endsWith(".pdf"))]);
  }

  async function uploadAll() {
    setBusy(true);
    let ok = 0;
    for (const f of files) {
      setStatus((s) => ({ ...s, [f.name]: "Uploading…" }));
      try {
        await api.upload(f, collectionId);
        setStatus((s) => ({ ...s, [f.name]: "Added" }));
        ok++;
      } catch (e) {
        setStatus((s) => ({ ...s, [f.name]: e instanceof Error ? e.message : "Failed" }));
      }
    }
    setBusy(false);
    if (ok === files.length) onDone();
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(e: DragEvent) => (e.preventDefault(), setDrag(true))}
        onDragLeave={() => setDrag(false)}
        onDrop={(e: DragEvent) => (e.preventDefault(), setDrag(false), pick(e.dataTransfer.files))}
        className={`flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center ${drag ? "border-brand bg-brand-soft" : "border-line"}`}
      >
        <FileUp className="size-6 text-brand" aria-hidden />
        <p className="text-sm">Drop PDFs here or</p>
        <Button variant="outline" onClick={() => input.current?.click()}>
          Choose files
        </Button>
        <p className="text-xs text-muted-foreground">PDF only · up to 25 MB and 100 pages each · text-based (not scanned)</p>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => pick(e.target.files)} />
      </div>
      {files.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {files.map((f) => (
            <li key={f.name} className="flex justify-between gap-3">
              <span className="truncate">{f.name}</span>
              <span className="shrink-0 text-muted-foreground">{status[f.name] ?? `${(f.size / 1e6).toFixed(1)} MB`}</span>
            </li>
          ))}
        </ul>
      )}
      <Button className="h-11" disabled={!files.length || busy} onClick={uploadAll}>
        {busy && <Loader2 className="animate-spin" aria-hidden />} Upload {files.length || ""} {files.length === 1 ? "file" : "files"}
      </Button>
    </div>
  );
}

function IdTab({ collectionId, onDone }: { collectionId?: string | null; onDone: () => void }) {
  const [value, setValue] = useState("");
  const kind = detect(value);
  const m = useMutation({
    mutationFn: () => api.importPaper(kind!.source, value.trim(), collectionId),
    onSuccess: onDone,
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (kind) m.mutate();
      }}
    >
      <label htmlFor="import-id" className="text-sm font-medium">
        arXiv ID or URL, DOI, or a direct PDF link
      </label>
      <Input
        id="import-id"
        autoFocus
        className="h-11"
        placeholder="1706.03762 · 10.48550/arXiv.2005.14165 · https://…/paper.pdf"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {value && (kind ? `Looks like: ${kind.label}` : "Not recognised yet — paste an arXiv ID, DOI or https link.")}
      </p>
      {m.isError && (
        <p role="alert" className="text-sm text-danger">
          {(m.error as ApiError).message}
        </p>
      )}
      <Button type="submit" className="h-11" disabled={!kind || m.isPending}>
        {m.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Plus aria-hidden />} Import
      </Button>
      <button
        type="button"
        className="text-left text-sm text-brand underline-offset-2 hover:underline"
        onClick={() => setValue("1706.03762")}
      >
        Try a classic: Attention Is All You Need
      </button>
    </form>
  );
}

export function SearchTab({ collectionId, onAdded }: { collectionId?: string | null; onAdded?: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<DiscoverResult[] | null>(null);
  const [added, setAdded] = useState<Record<string, string>>({});
  const search = useMutation({ mutationFn: () => api.discover(q.trim()), onSuccess: setResults });

  async function add(r: DiscoverResult) {
    const key = r.arxiv_id ?? r.doi ?? r.title ?? "";
    setAdded((a) => ({ ...a, [key]: "Adding…" }));
    try {
      if (r.arxiv_id) await api.importPaper("arxiv", r.arxiv_id, collectionId);
      else if (r.doi) await api.importPaper("doi", r.doi, collectionId);
      setAdded((a) => ({ ...a, [key]: "Added" }));
      onAdded?.();
    } catch (e) {
      setAdded((a) => ({ ...a, [key]: e instanceof Error ? e.message : "Failed" }));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim().length > 1) search.mutate();
        }}
      >
        <Input
          aria-label="Search papers"
          className="h-11"
          placeholder="e.g. retrieval augmented generation evaluation"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Button type="submit" className="h-11" disabled={search.isPending}>
          {search.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Search aria-hidden />} Search
        </Button>
      </form>
      {search.isError && <p className="text-sm text-danger">{(search.error as Error).message}</p>}
      {results && !results.length && <p className="text-sm text-muted-foreground">No open-access results. Try other words.</p>}
      <ul className="flex flex-col gap-3">
        {results?.map((r) => {
          const key = r.arxiv_id ?? r.doi ?? r.title ?? "";
          return (
            <li key={key} className="rounded-xl border border-line p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-medium leading-snug">{r.title}</h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {r.authors.slice(0, 4).join(", ")}
                    {r.authors.length > 4 && " et al."} · {r.year ?? "n.d."}
                    {r.venue ? ` · ${r.venue}` : ""}
                    {r.citation_count != null ? ` · ${r.citation_count} citations` : ""}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant={r.in_library ? "outline" : "default"}
                  disabled={r.in_library || !r.importable || !!added[key]}
                  title={!r.importable ? "No open-access PDF available" : undefined}
                  onClick={() => void add(r)}
                >
                  {r.in_library ? "In library" : (added[key] ?? "Add")}
                </Button>
              </div>
              {r.abstract && <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{r.abstract}</p>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
