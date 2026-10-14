"use client";

import { AlertTriangle, Loader2 } from "lucide-react";

import { CitationChip } from "@/components/markdown";
import type { Cell, Citation, Comparison } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Spreadsheet-like comparison matrix: sticky paper column, one column per question. */
export function Matrix({
  cmp,
  onCite,
  running,
}: {
  cmp: Pick<Comparison, "columns" | "cells" | "papers" | "paper_ids">;
  onCite?: (c: Citation) => void;
  running?: boolean;
}) {
  return (
    <div className="overflow-auto rounded-xl border border-line">
      <table className="min-w-full border-collapse text-[13px]">
        <thead className="sticky top-0 z-10 bg-surface">
          <tr>
            <th className="sticky left-0 z-20 min-w-48 border-b border-r border-line bg-surface p-3 text-left font-semibold">Paper</th>
            {cmp.columns.map((c) => (
              <th key={c.key} title={c.question} className="min-w-56 border-b border-line p-3 text-left font-semibold">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {cmp.paper_ids.map((pid) => {
            const p = cmp.papers.find((x) => x.id === pid);
            const cells = cmp.cells[pid] ?? {};
            return (
              <tr key={pid} className="align-top">
                <th scope="row" className="sticky left-0 z-[1] border-b border-r border-line bg-surface p-3 text-left font-medium">
                  {p?.title ?? "Untitled"}
                  <div className="text-xs font-normal text-muted-foreground">
                    {p?.authors[0]}
                    {p && p.authors.length > 1 ? " et al." : ""} {p?.year ?? ""}
                  </div>
                </th>
                {cmp.columns.map((c) => (
                  <td key={c.key} className="border-b border-line p-3">
                    <CellView cell={cells[c.key]} running={running} onCite={onCite} />
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CellView({ cell, running, onCite }: { cell?: Cell; running?: boolean; onCite?: (c: Citation) => void }) {
  if (!cell)
    return running ? (
      <span className="flex items-center gap-1 text-muted-foreground"><Loader2 className="size-3 animate-spin" aria-hidden /> filling…</span>
    ) : (
      <span className="text-muted-foreground">—</span>
    );
  if (cell.status === "not_found" || !cell.value) return <span className="text-muted-foreground">Not stated</span>;
  const warn = cell.status === "unsupported" || cell.status === "partial";
  return (
    <span className={cn(warn && "text-warn")}>
      {warn && <AlertTriangle className="mr-1 inline size-3" aria-label={`Verification: ${cell.status}`} />}
      {cell.value}
      {cell.citations.map((ct, i) => (
        <CitationChip key={i} c={{ ...ct, n: i + 1 }} n={i + 1} onClick={onCite} />
      ))}
    </span>
  );
}
