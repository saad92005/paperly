"use client";

import { authClient } from "@/lib/auth-client";

export type SessionState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "signed-out" }
  | { status: "signed-in"; user: { id: string; email: string; name: string | null } };

export function useSession(): SessionState {
  const { data, isPending, error } = authClient.useSession();
  if (isPending) return { status: "loading" };
  if (error) return { status: "error", message: error.message ?? "Sign-in service unavailable." };
  if (!data) return { status: "signed-out" };
  return {
    status: "signed-in",
    user: { id: data.user.id, email: data.user.email, name: data.user.name || null },
  };
}

// Short-lived JWT for the FastAPI service; refreshed a minute before it expires.
let cached: { token: string; exp: number } | null = null;
const REFRESH_MARGIN_S = 60;

function expOf(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return typeof payload.exp === "number" ? payload.exp : 0;
  } catch {
    return 0;
  }
}

export async function apiToken(): Promise<string | null> {
  const now = Date.now() / 1000;
  if (cached && cached.exp - REFRESH_MARGIN_S > now) return cached.token;
  const { data } = await authClient.token();
  if (!data?.token) {
    cached = null;
    return null;
  }
  cached = { token: data.token, exp: expOf(data.token) };
  return cached.token;
}

export function clearApiToken() {
  cached = null;
}
