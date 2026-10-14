"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Profile } from "@/lib/api";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { ErrorState, Skeleton, selectClass } from "@/components/bits";
import { LANGS } from "@/components/reader/chat-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, downloadFile, queryKeys } from "@/lib/api";
import { authClient } from "@/lib/auth-client";
import { clearApiToken } from "@/lib/session";

export default function SettingsPage() {
  const { userId, ready, email } = useRequireUser();
  const qc = useQueryClient();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const me = useQuery({ queryKey: queryKeys.me(userId), queryFn: api.me, enabled: ready });
  const usage = useQuery({ queryKey: queryKeys.usage(userId), queryFn: api.usage, enabled: ready });

  async function exportData() {
    const [papers, collections] = await Promise.all([api.papers(), api.collections()]);
    const notes = await Promise.all(papers.items.map(async (p) => ({ paper: p.title, notes: await api.notes(p.id) })));
    const threads = await api.threads();
    const chats = await Promise.all(threads.map((t) => api.thread(t.id)));
    downloadFile("paperly-export.json", JSON.stringify({ profile: me.data, collections, papers: papers.items, notes, chats }, null, 2), "application/json");
  }

  return (
    <AppShell>
      <PageTitle title="Settings" sub={email} />
      {me.isPending ? (
        <Skeleton className="h-64 max-w-2xl" />
      ) : me.isError ? (
        <ErrorState error={me.error} onRetry={() => void me.refetch()} />
      ) : (
        <div className="flex max-w-2xl flex-col gap-6">
          <ProfileForm key={me.dataUpdatedAt} profile={me.data} onSaved={() => void qc.invalidateQueries({ queryKey: queryKeys.me(userId) })} />

          <Section title="Appearance">
            <div className="flex gap-2">
              {["system", "light", "dark"].map((t) => (
                <Button key={t} variant={theme === t ? "default" : "outline"} className="h-10 capitalize" onClick={() => setTheme(t)}>
                  {t}
                </Button>
              ))}
            </div>
          </Section>

          <Section title="Usage today">
            {usage.data ? (
              <div className="grid gap-3">
                {(["questions", "imports", "compares"] as const).map((k) => {
                  const used = usage.data.used[k];
                  const limit = usage.data.limits[k];
                  return (
                    <div key={k}>
                      <div className="flex justify-between text-sm capitalize">
                        <span>{k}</span>
                        <span className="tabular-nums text-muted-foreground">{used} / {limit}</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
                        <div className="h-full bg-brand" style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} />
                      </div>
                    </div>
                  );
                })}
                <p className="text-xs text-muted-foreground">Resets at {new Date(usage.data.reset_at).toLocaleString()}.</p>
              </div>
            ) : (
              <Skeleton className="h-20" />
            )}
          </Section>

          <Section title="Data and privacy">
            <p className="text-sm text-muted-foreground">
              Paper excerpts you ask about are sent to the configured AI provider (Groq, Google Gemini or OpenRouter free
              tiers) to write answers. Your PDFs, notes and chats are never shared or used for training by Paperly.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="h-10" onClick={() => void exportData()}>Download my data</Button>
              <Button
                variant="destructive"
                className="h-10"
                onClick={async () => {
                  if (window.prompt('This deletes your account, papers, notes and chats forever. Type "delete" to confirm.') !== "delete") return;
                  await api.deleteMe();
                  clearApiToken();
                  await authClient.signOut();
                  router.replace("/");
                }}
              >
                Delete account
              </Button>
            </div>
          </Section>
        </div>
      )}
    </AppShell>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5">
      <h2 className="font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function ProfileForm({ profile, onSaved }: { profile: Profile; onSaved: () => void }) {
  const [name, setName] = useState(profile.display_name ?? "");
  const [locale, setLocale] = useState(profile.locale);
  const [level, setLevel] = useState(profile.explain_level);
  const save = useMutation({
    mutationFn: () => api.updateMe({ display_name: name || null, locale, explain_level: level }),
    onSuccess: onSaved,
  });
  return (
    <Section title="Profile and answers">
      <label className="flex flex-col gap-1 text-sm">
        Display name
        <Input className="h-10" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Default answer language
        <select className={selectClass + " h-10"} value={locale} onChange={(e) => setLocale(e.target.value)}>
          {LANGS.filter(([v]) => v !== "auto").map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Default explanation level
        <select className={selectClass + " h-10"} value={level} onChange={(e) => setLevel(e.target.value as typeof level)}>
          <option value="eli5">ELI5 — plain words and analogies</option>
          <option value="student">Student — defines terms</option>
          <option value="expert">Expert — dense and precise</option>
        </select>
      </label>
      <div className="flex items-center gap-3">
        <Button className="h-10" disabled={save.isPending} onClick={() => save.mutate()}>Save</Button>
        {save.isSuccess && <span className="text-sm text-ok">Saved</span>}
        {save.isError && <span className="text-sm text-danger">{(save.error as Error).message}</span>}
      </div>
    </Section>
  );
}
