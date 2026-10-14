"use client";

import { useQuery } from "@tanstack/react-query";
import { Command, FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, queryKeys } from "@/lib/api";
import { useSession } from "@/lib/session";

type Item = { id: string; label: string; hint?: string; run: () => void };

/** ⌘/Ctrl K: jump to any page or paper. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const router = useRouter();
  const session = useSession();
  const userId = session.status === "signed-in" ? session.user.id : "";
  const inputRef = useRef<HTMLInputElement>(null);
  const papers = useQuery({
    queryKey: queryKeys.papers(userId),
    queryFn: () => api.papers(),
    enabled: open && !!userId,
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const go = (href: string) => () => {
      setOpen(false);
      router.push(href);
    };
    const pages: Item[] = [
      { id: "lib", label: "Go to Library", run: go("/library") },
      { id: "cmp", label: "Go to Compare", run: go("/compare") },
      { id: "dis", label: "Go to Discover", run: go("/discover") },
      { id: "stu", label: "Go to Study", run: go("/study") },
      { id: "rev", label: "Go to Reviews", run: go("/reviews") },
      { id: "set", label: "Go to Settings", run: go("/settings") },
    ];
    const ps: Item[] = (papers.data?.items ?? []).map((p) => ({
      id: p.id,
      label: p.title ?? p.source_ref ?? "Untitled",
      hint: p.year ? String(p.year) : undefined,
      run: go(`/paper/${p.id}`),
    }));
    const needle = q.trim().toLowerCase();
    return [...pages, ...ps].filter((i) => !needle || i.label.toLowerCase().includes(needle)).slice(0, 12);
  }, [papers.data, q, router]);

  return (
    <>
      <Button variant="ghost" size="lg" onClick={() => setOpen(true)} aria-label="Open command palette">
        <Command aria-hidden /> <span className="hidden text-xs text-muted-foreground lg:inline">Ctrl K</span>
      </Button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh]"
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-label="Command palette"
            className="w-full max-w-lg overflow-hidden rounded-xl border border-line bg-surface shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setActive(0);
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, items.length - 1));
                else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
                else if (e.key === "Enter") items[active]?.run();
              }}
              placeholder="Search papers and pages…"
              className="h-12 w-full border-b border-line bg-transparent px-4 text-sm outline-none"
            />
            <ul className="max-h-80 overflow-auto p-1">
              {items.map((it, i) => (
                <li key={it.id}>
                  <button
                    className={`flex w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-sm ${i === active ? "bg-brand-soft" : ""}`}
                    onMouseEnter={() => setActive(i)}
                    onClick={it.run}
                  >
                    <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <span className="truncate">{it.label}</span>
                    {it.hint && <span className="ml-auto text-xs text-muted-foreground">{it.hint}</span>}
                  </button>
                </li>
              ))}
              {!items.length && <li className="px-3 py-6 text-center text-sm text-muted-foreground">No matches</li>}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
