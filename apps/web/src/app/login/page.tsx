"use client";

import { Loader2, Mail } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";
import { env } from "@/lib/env";
import { useSession } from "@/lib/session";
import { site } from "@/lib/site";

type Mode = "magic" | "password";
type FormState =
  | { kind: "idle" }
  | { kind: "busy" }
  | { kind: "sent"; email: string }
  | { kind: "error"; message: string };

const CALLBACK = "/library";

export default function LoginPage() {
  const session = useSession();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("magic");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [form, setForm] = useState<FormState>({ kind: "idle" });

  useEffect(() => {
    if (session.status === "signed-in") router.replace(CALLBACK);
  }, [session.status, router]);

  async function sendMagicLink(e: FormEvent) {
    e.preventDefault();
    setForm({ kind: "busy" });
    const { error } = await authClient.signIn.magicLink({ email, callbackURL: CALLBACK });
    setForm(error ? { kind: "error", message: error.message ?? "Couldn't send the link." } : { kind: "sent", email });
  }

  async function passwordAuth(e: FormEvent, action: "in" | "up") {
    e.preventDefault();
    setForm({ kind: "busy" });
    const { error } =
      action === "in"
        ? await authClient.signIn.email({ email, password })
        : await authClient.signUp.email({ email, password, name: email.split("@")[0] });
    if (error) {
      const message =
        error.status === 429
          ? "Too many attempts. Wait a minute and try again, or use a magic link instead."
          : error.status === 401
            ? "Wrong email or password. Try again, or sign in with a magic link."
            : (error.message ?? "Sign-in failed.");
      setForm({ kind: "error", message });
      return;
    }
    // Next keeps this page's state when navigating back, so never leave it "busy".
    setForm({ kind: "idle" });
    setPassword("");
    router.replace(CALLBACK);
  }

  async function signInWithGoogle() {
    const { error } = await authClient.signIn.social({ provider: "google", callbackURL: CALLBACK });
    if (error) setForm({ kind: "error", message: error.message ?? "Google sign-in failed." });
  }

  const busy = form.kind === "busy";

  return (
    <>
      <AppHeader />
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="text-xl">Sign in to {site.name}</CardTitle>
            <CardDescription>Your library, notes and chats stay private to you.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {env.googleEnabled && (
              <>
                <Button variant="outline" className="h-11" onClick={signInWithGoogle}>
                  Continue with Google
                </Button>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
                </div>
              </>
            )}

            {form.kind === "sent" ? (
              <p role="status" className="text-sm">
                Check <strong>{form.email}</strong> for a sign-in link.
              </p>
            ) : (
              <form
                onSubmit={mode === "magic" ? sendMagicLink : (e) => passwordAuth(e, "in")}
                className="flex flex-col gap-3"
              >
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
                {mode === "password" && (
                  <>
                    <label htmlFor="password" className="text-sm font-medium">
                      Password
                    </label>
                    <Input
                      id="password"
                      type="password"
                      required
                      minLength={8}
                      autoComplete="current-password"
                      className="h-11"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </>
                )}
                <Button type="submit" className="h-11" disabled={busy}>
                  {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Mail aria-hidden />}
                  {mode === "magic" ? "Email me a sign-in link" : "Sign in"}
                </Button>
                {mode === "password" && (
                  <Button
                    type="button"
                    variant="outline"
                    className="h-11"
                    disabled={busy}
                    onClick={(e) => passwordAuth(e, "up")}
                  >
                    Create account
                  </Button>
                )}
                <Button
                  type="button"
                  variant="link"
                  className="h-11"
                  onClick={() => {
                    setMode(mode === "magic" ? "password" : "magic");
                    setForm({ kind: "idle" });
                  }}
                >
                  {mode === "magic" ? "Use a password instead" : "Use a magic link instead"}
                </Button>
              </form>
            )}
            {(form.kind === "error" || session.status === "error") && (
              <p role="alert" className="text-sm text-danger">
                {form.kind === "error" ? form.message : session.status === "error" ? session.message : ""}
              </p>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
