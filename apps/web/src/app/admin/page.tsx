"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { ErrorState, Skeleton } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { api, queryKeys } from "@/lib/api";

type Metrics = {
  users: number;
  papers: number;
  chunks: number;
  answers: number;
  db_bytes: number;
  blob_bytes: number;
  thumbs_up: number;
  thumbs_down: number;
  quota_hits: number;
  jobs: Record<string, number>;
  providers: { provider: string; calls: number; error_rate: number; p95_ms: number }[];
  answers_7d: { p50_ms: number | null; p95_ms: number | null; grounded_rate: number | null } | null;
  llm_providers: string[];
};

const mb = (b: number) => `${(b / 1024 / 1024).toFixed(1)} MB`;

export default function AdminPage() {
  const { userId, ready } = useRequireUser();
  const qc = useQueryClient();
  const m = useQuery({ queryKey: queryKeys.admin(userId), queryFn: async () => (await api.adminMetrics()) as unknown as Metrics, enabled: ready, retry: 0 });
  const jobs = useQuery({ queryKey: ["adminJobs", userId], queryFn: api.adminJobs, enabled: ready && m.isSuccess });
  return (
    <AppShell>
      <PageTitle title="Admin" sub="Operational metrics (admins only)" />
      {m.isPending ? (
        <Skeleton className="h-64" />
      ) : m.isError ? (
        <ErrorState error={m.error} title="Admins only" />
      ) : (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[
              ["Users", m.data.users],
              ["Papers", m.data.papers],
              ["Chunks", m.data.chunks],
              ["Answers", m.data.answers],
              ["Database", mb(m.data.db_bytes)],
              ["PDF blobs", mb(m.data.blob_bytes)],
              ["👍 / 👎", `${m.data.thumbs_up} / ${m.data.thumbs_down}`],
              ["Quota hits today", m.data.quota_hits],
              ["Answer p50 / p95", m.data.answers_7d ? `${Math.round(m.data.answers_7d.p50_ms ?? 0)} / ${Math.round(m.data.answers_7d.p95_ms ?? 0)} ms` : "—"],
              ["Grounded rate (7d)", m.data.answers_7d?.grounded_rate != null ? `${Math.round(m.data.answers_7d.grounded_rate * 100)}%` : "—"],
              ["LLM providers", m.data.llm_providers.join(", ") || "none (extractive)"],
              ["Jobs", Object.entries(m.data.jobs).map(([k, v]) => `${k} ${v}`).join(" · ")],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-xl border border-line bg-surface p-4">
                <p className="text-xs text-muted-foreground">{k}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{v}</p>
              </div>
            ))}
          </div>
          <section>
            <h2 className="mb-2 font-semibold">Providers (7 days)</h2>
            <table className="w-full text-sm">
              <thead><tr className="text-left text-muted-foreground"><th>Provider</th><th>Calls</th><th>Error rate</th><th>p95</th></tr></thead>
              <tbody>
                {m.data.providers.map((p) => (
                  <tr key={p.provider}><td>{p.provider}</td><td>{p.calls}</td><td>{Math.round(p.error_rate * 100)}%</td><td>{Math.round(p.p95_ms)} ms</td></tr>
                ))}
              </tbody>
            </table>
          </section>
          <section>
            <h2 className="mb-2 font-semibold">Failed jobs</h2>
            <ul className="flex flex-col gap-2 text-sm">
              {(jobs.data ?? []).map((j) => (
                <li key={String(j.id)} className="flex items-center gap-3 rounded-lg border border-line p-3">
                  <span className="font-mono text-xs">{String(j.type)}</span>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">{String(j.error)}</span>
                  <Button size="sm" variant="outline" onClick={async () => { await api.adminRetry(String(j.id)); void qc.invalidateQueries({ queryKey: ["adminJobs"] }); }}>
                    Retry
                  </Button>
                </li>
              ))}
              {jobs.data?.length === 0 && <li className="text-muted-foreground">None 🎉</li>}
            </ul>
          </section>
        </div>
      )}
    </AppShell>
  );
}
