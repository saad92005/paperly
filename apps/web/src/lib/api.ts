import type { components } from "@paperly/api-types";

import { env } from "@/lib/env";
import { apiToken } from "@/lib/session";

export type Profile = components["schemas"]["Profile"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];
export type Health = components["schemas"]["Health"];

type ErrorBody = {
  error?: { code?: string; message?: string; request_id?: string | null };
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  { auth = true }: { auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (auth) {
    const token = await apiToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(`${env.apiBaseUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", "Can't reach the Paperly server. Is it running?", null);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as ErrorBody;
    throw new ApiError(
      res.status,
      body.error?.code ?? "internal",
      body.error?.message ?? `Request failed (${res.status}).`,
      body.error?.request_id ?? res.headers.get("X-Request-ID"),
    );
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => apiFetch<Health>("/health", {}, { auth: false }),
  me: () => apiFetch<Profile>("/v1/me"),
  updateMe: (patch: ProfileUpdate) =>
    apiFetch<Profile>("/v1/me", { method: "PATCH", body: JSON.stringify(patch) }),
};
