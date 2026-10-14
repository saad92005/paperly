"use client";

import {
  BookOpen,
  Brain,
  Columns3,
  Compass,
  FileText,
  Library,
  LogOut,
  Settings,
  Shield,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { CommandPalette } from "@/components/command-palette";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { authClient } from "@/lib/auth-client";
import { clearApiToken, useSession } from "@/lib/session";
import { site } from "@/lib/site";
import { cn } from "@/lib/utils";

const NAV: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/library", label: "Library", icon: Library },
  { href: "/compare", label: "Compare", icon: Columns3 },
  { href: "/discover", label: "Discover", icon: Compass },
  { href: "/study", label: "Study", icon: Brain },
  { href: "/reviews", label: "Reviews", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

/** Redirects to /login when signed out; returns the user id once signed in ("" while loading). */
export function useRequireUser(): { userId: string; ready: boolean; email: string } {
  const session = useSession();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (session.status === "signed-out") router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [session.status, router, path]);
  return session.status === "signed-in"
    ? { userId: session.user.id, ready: true, email: session.user.email }
    : { userId: "", ready: false, email: "" };
}

export function AppShell({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const session = useSession();
  const router = useRouter();
  const path = usePathname();

  async function signOut() {
    // User-scoped queries are keyed by user id (see lib/api.ts), so they simply go idle here.
    clearApiToken();
    await authClient.signOut();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface/95 px-4 backdrop-blur">
        <Link href="/library" className="flex items-center gap-2 font-semibold tracking-tight">
          <BookOpen className="size-5 text-brand" aria-hidden />
          {site.name}
        </Link>
        <div className="flex items-center gap-1">
          <CommandPalette />
          <ThemeToggle />
          {session.status === "signed-in" && (
            <Button variant="ghost" size="lg" onClick={signOut} aria-label="Sign out">
              <LogOut aria-hidden /> <span className="hidden sm:inline">Sign out</span>
            </Button>
          )}
        </div>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Main" className="hidden w-52 shrink-0 flex-col gap-1 border-r border-line bg-surface p-3 md:flex">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium text-muted-foreground hover:bg-brand-soft hover:text-ink",
                path.startsWith(href) && "bg-brand-soft text-ink",
              )}
            >
              <Icon className="size-4" aria-hidden /> {label}
            </Link>
          ))}
          <Link
            href="/admin"
            className="mt-auto flex h-9 items-center gap-3 rounded-lg px-3 text-xs text-muted-foreground hover:text-ink"
          >
            <Shield className="size-3.5" aria-hidden /> Admin
          </Link>
        </nav>
        <main className={cn("min-w-0 flex-1 pb-16 md:pb-0", !wide && "mx-auto w-full max-w-6xl px-4 py-6 md:px-8")}>
          {children}
        </main>
      </div>
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-surface md:hidden"
      >
        {NAV.slice(0, 5).map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground",
              path.startsWith(href) && "text-brand",
            )}
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function PageTitle({ title, children, sub }: { title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted-foreground">{sub}</p>}
      </div>
      {children && <div className="flex flex-wrap gap-2">{children}</div>}
    </div>
  );
}
