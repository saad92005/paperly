"use client";

import { BookOpen, LogOut } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { useSession } from "@/lib/session";
import { site } from "@/lib/site";
import { getSupabase } from "@/lib/supabase";

export function AppHeader() {
  const session = useSession();
  const router = useRouter();

  async function signOut() {
    await getSupabase()?.auth.signOut();
    router.replace("/login");
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
