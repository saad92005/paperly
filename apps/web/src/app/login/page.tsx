"use client";

import { Loader2, Mail } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AppHeader } from "@/components/app-header";
import { SetupNotice } from "@/components/setup-notice";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useSession } from "@/lib/session";
import { site } from "@/lib/site";
import { getSupabase } from "@/lib/supabase";

type FormState =
  | { kind: "idle" }
  | { kind: "sending" }
  | { kind: "sent"; email: string }
  | { kind: "error"; message: string };

function redirectTo() {
  return `${window.location.origin}/library`;
}

export default function LoginPage() {
  const session = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [form, setForm] = useState<FormState>({ kind: "idle" });

  useEffect(() => {
    if (session.status === "signed-in") router.replace("/library");
  }, [session.status, router]);

  async function sendMagicLink(e: FormEvent) {
    e.preventDefault();
    const supabase = getSupabase();
    if (!supabase) return;
    setForm({ kind: "sending" });
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: redirectTo() },
    });
    setForm(error ? { kind: "error", message: error.message } : { kind: "sent", email });
  }

  async function signInWithGoogle() {
    const { error } =
      (await getSupabase()?.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: redirectTo() },
      })) ?? {};
    if (error) setForm({ kind: "error", message: error.message });
  }

  return (
    <>
      <AppHeader />
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        {session.status === "unconfigured" ? (
          <SetupNotice />
        ) : (
          <Card className="w-full max-w-sm">
            <CardHeader>
              <CardTitle className="text-xl">Sign in to {site.name}</CardTitle>
              <CardDescription>Your library, notes and chats stay private to you.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <Button variant="outline" className="h-11" onClick={signInWithGoogle}>
                Continue with Google
              </Button>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
              </div>
              {form.kind === "sent" ? (
                <p role="status" className="text-sm">
                  Check <strong>{form.email}</strong> for a sign-in link.
                </p>
              ) : (
                <form onSubmit={sendMagicLink} className="flex flex-col gap-3">
                  <label htmlFor="email" className="text-sm font-medium">
                    Email
                  </label>
                  <Input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    placeholder="you@university.edu"
                    className="h-11"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                  <Button type="submit" className="h-11" disabled={form.kind === "sending"}>
                    {form.kind === "sending" ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <Mail aria-hidden />
                    )}
                    Email me a sign-in link
                  </Button>
                </form>
              )}
              {form.kind === "error" && (
                <p role="alert" className="text-sm text-danger">
                  {form.message}
                </p>
              )}
            </CardContent>
          </Card>
        )}
      </main>
    </>
  );
}
