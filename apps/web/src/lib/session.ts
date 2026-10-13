"use client";

import type { Session } from "@supabase/supabase-js";
import { useSyncExternalStore } from "react";

import { getSupabase } from "@/lib/supabase";

export type SessionState =
  | { status: "loading" }
  | { status: "unconfigured" }
  | { status: "signed-out" }
  | { status: "signed-in"; session: Session };

const LOADING: SessionState = { status: "loading" };
const UNCONFIGURED: SessionState = { status: "unconfigured" };
const SIGNED_OUT: SessionState = { status: "signed-out" };

let state: SessionState = LOADING;
let started = false;
const listeners = new Set<() => void>();

function set(next: SessionState) {
  state = next;
  listeners.forEach((l) => l());
}

function start() {
  if (started) return;
  started = true;
  const supabase = getSupabase();
  if (!supabase) {
    set(UNCONFIGURED);
    return;
  }
  // onAuthStateChange fires INITIAL_SESSION once the stored session (or URL code) is processed.
  supabase.auth.onAuthStateChange((_event, session) => {
    set(session ? { status: "signed-in", session } : SIGNED_OUT);
  });
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  start();
  return () => listeners.delete(listener);
}

export function useSession(): SessionState {
  return useSyncExternalStore(
    subscribe,
    () => state,
    () => LOADING,
  );
}

export function currentAccessToken(): string | null {
  return state.status === "signed-in" ? state.session.access_token : null;
}
