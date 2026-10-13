"use client";

import { useQuery } from "@tanstack/react-query";
import { FileUp, Link2, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppHeader } from "@/components/app-header";
import { SetupNotice } from "@/components/setup-notice";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { useSession } from "@/lib/session";

const IMPORT_TILES = [
  { icon: FileUp, title: "Upload PDFs", body: "Drag and drop up to 25 MB each." },
  { icon: Link2, title: "arXiv or DOI", body: "Paste an ID like 1706.03762." },
  { icon: Search, title: "Search papers", body: "Find open-access papers to import." },
];

export default function LibraryPage() {
  const session = useSession();
  const router = useRouter();
  const signedIn = session.status === "signed-in";
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, enabled: signedIn });

  useEffect(() => {
    if (session.status === "signed-out") router.replace("/login");
  }, [session.status, router]);

  return (
    <>
      <AppHeader />
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-10">
        {session.status === "unconfigured" ? (
          <div className="flex justify-center">
            <SetupNotice />
          </div>
        ) : !signedIn || me.isPending ? (
          <LibrarySkeleton />
        ) : me.isError ? (
          <LoadError error={me.error} onRetry={() => void me.refetch()} />
        ) : (
          <>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Your library</h1>
              <p className="text-muted-foreground">
                Welcome{me.data.display_name ? `, ${me.data.display_name}` : ""}. Add your first paper
                to start reading and asking questions.
              </p>
            </div>
            <section aria-label="Add papers" className="grid gap-4 sm:grid-cols-3">
              {IMPORT_TILES.map(({ icon: Icon, title, body }) => (
                <div key={title} className="flex flex-col gap-2 rounded-xl border border-line bg-surface p-5">
                  <Icon className="size-5 text-brand" aria-hidden />
                  <h2 className="font-semibold">{title}</h2>
                  <p className="text-sm text-muted-foreground">{body}</p>
                  <p className="text-xs text-muted-foreground">Coming in Phase 1</p>
                </div>
              ))}
            </section>
            <p className="text-sm text-muted-foreground">
              Try with a classic: <em>Attention Is All You Need</em> — one-click import arrives with ingestion.
            </p>
          </>
        )}
      </main>
    </>
  );
}

function LibrarySkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading library" className="flex flex-col gap-6">
      <div className="h-8 w-48 animate-pulse rounded-md bg-muted" />
      <div className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-32 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    </div>
  );
}

function LoadError({ error, onRetry }: { error: Error; onRetry: () => void }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border border-line bg-surface p-6">
      <h1 className="text-lg font-semibold">We couldn&apos;t load your library</h1>
      <p className="text-muted-foreground">{error.message}</p>
      <div className="flex gap-2">
        <Button onClick={onRetry} className="h-11">
          Retry
        </Button>
        {requestId && (
          <Button
            variant="outline"
            className="h-11"
            onClick={() => void navigator.clipboard.writeText(requestId)}
          >
            Copy error ID
          </Button>
        )}
      </div>
    </div>
  );
}
