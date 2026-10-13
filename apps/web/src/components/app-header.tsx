"use client";

import { BookOpen, LogOut } from "lucide-react";
import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";
import { clearApiToken, useSession } from "@/lib/session";
import { site } from "@/lib/site";

export function AppHeader() {
  const session = useSession();

  async function signOut() {
    clearApiToken();
    await authClient.signOut();
    // Full reload drops every cached query and page state from the signed-in session.
    window.location.assign("/login");
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-line bg-surface px-4">
      <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
        <BookOpen className="size-5 text-brand" aria-hidden />
        {site.name}
      </Link>
      <div className="flex items-center gap-1">
        <ThemeToggle />
        {session.status === "signed-in" && (
          <Button variant="ghost" size="lg" onClick={signOut}>
            <LogOut aria-hidden /> Sign out
          </Button>
        )}
      </div>
    </header>
  );
}
