"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { Empty, ErrorState, Skeleton } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { api, queryKeys } from "@/lib/api";

const GRADES: [string, number, string][] = [
  ["Again", 1, "border-danger/40"],
  ["Hard", 3, "border-warn/40"],
  ["Good", 4, "border-ok/40"],
  ["Easy", 5, "border-brand/40"],
];

export default function StudyPage() {
  const { userId, ready } = useRequireUser();
  const qc = useQueryClient();
  const due = useQuery({ queryKey: queryKeys.due(userId), queryFn: api.due, enabled: ready });
  const [i, setI] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [done, setDone] = useState(0);
  const cards = due.data ?? [];
  const card = cards[i];

  async function grade(g: number) {
    if (!card) return;
    await api.reviewCard(card.id, g);
    setFlipped(false);
    setDone((d) => d + 1);
    if (i + 1 < cards.length) setI(i + 1);
    else {
      setI(0);
      void qc.invalidateQueries({ queryKey: queryKeys.due(userId) });
    }
  }

  return (
    <AppShell>
      <PageTitle title="Study" sub={due.data ? `${cards.length} card${cards.length === 1 ? "" : "s"} due · ${done} reviewed this session` : undefined} />
      {due.isPending ? (
        <Skeleton className="mx-auto h-64 max-w-xl" />
      ) : due.isError ? (
        <ErrorState error={due.error} onRetry={() => void due.refetch()} />
      ) : !card ? (
        <Empty title="Nothing due right now">
          Generate flashcards from a paper&apos;s <strong>Cards</strong> tab in the reader. Paperly schedules reviews with SM-2 spaced repetition.
        </Empty>
      ) : (
        <div className="mx-auto flex max-w-xl flex-col gap-4">
          <button
            onClick={() => setFlipped((f) => !f)}
            className="flex min-h-64 flex-col justify-center gap-3 rounded-2xl border border-line bg-surface p-8 text-center shadow-sm"
            aria-label={flipped ? "Show question" : "Show answer"}
          >
            <span className="text-xs uppercase tracking-wide text-muted-foreground">{card.paper_title ?? "Paper"}</span>
            <span className="font-serif text-xl leading-relaxed">{flipped ? card.back : card.front}</span>
            {!flipped && <span className="text-xs text-muted-foreground">Tap to reveal</span>}
            {flipped && card.citation && (
              <Link onClick={(e) => e.stopPropagation()} href={`/paper/${card.paper_id}?page=${card.citation.page}`} className="text-xs text-brand underline">
                Source: p.{card.citation.page} {card.citation.section ? `· ${card.citation.section}` : ""}
              </Link>
            )}
          </button>
          {flipped ? (
            <div className="grid grid-cols-4 gap-2">
              {GRADES.map(([label, g, cls]) => (
                <Button key={label} variant="outline" className={`h-12 ${cls}`} onClick={() => void grade(g)}>
                  {label}
                </Button>
              ))}
            </div>
          ) : (
            <Button className="h-12" onClick={() => setFlipped(true)}>Show answer</Button>
          )}
          <p className="text-center text-xs text-muted-foreground">Card {i + 1} of {cards.length}</p>
        </div>
      )}
    </AppShell>
  );
}
