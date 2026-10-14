import type { components } from "@paperly/api-types";

import { env } from "@/lib/env";
import { apiToken } from "@/lib/session";
import type {
  Chunk,
  Collection,
  Comparison,
  DiscoverResult,
  Flashcard,
  GlossaryTerm,
  Job,
  Level,
  Note,
  Paper,
  PaperCard,
  Reference,
  ReviewItem,
  Summary,
  Thread,
  ThreadDetail,
  Usage,
} from "@/lib/types";

export type Profile = components["schemas"]["Profile"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];
export type Health = components["schemas"]["Health"];

type ErrorBody = {
  error?: { code?: string; message?: string; request_id?: string | null; details?: Record<string, unknown> };
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function authHeaders(init?: HeadersInit): Promise<Headers> {
  const headers = new Headers(init);
  const token = await apiToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

export async function toApiError(res: Response): Promise<ApiError> {
  const body = (await res.json().catch(() => ({}))) as ErrorBody;
  return new ApiError(
    res.status,
    body.error?.code ?? "internal",
    body.error?.message ?? `Request failed (${res.status}).`,
    body.error?.request_id ?? res.headers.get("X-Request-ID"),
    body.error?.details ?? {},
  );
}

export async function rawFetch(path: string, init: RequestInit = {}, auth = true): Promise<Response> {
  const headers = auth ? await authHeaders(init.headers) : new Headers(init.headers);
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${env.apiBaseUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network", "Can't reach the Paperly server. Is it running?", null);
  }
  if (!res.ok) throw await toApiError(res);
  return res;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  { auth = true }: { auth?: boolean } = {},
): Promise<T> {
  const res = await rawFetch(path, init, auth);
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? await res.json() : await res.text()) as T;
}

/**
 * On serverless hosting the API has no always-on worker: queued jobs (indexing, summaries, comparisons…)
 * run inside POST /v1/worker/tick. Call this after enqueuing work and while waiting; it is throttled and
 * fire-and-forget. On container hosting the tick is a cheap no-op.
 */
let lastKick = 0;
export function kickWorker(force = false) {
  const now = Date.now();
  if (!force && now - lastKick < 12_000) return;
  lastKick = now;
  void rawFetch("/v1/worker/tick", { method: "POST" }).catch(() => undefined);
}

function kicked<T>(p: Promise<T>): Promise<T> {
  return p.then((r) => {
    kickWorker(true);
    return r;
  });
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const patch = (body: unknown): RequestInit => ({ method: "PATCH", body: JSON.stringify(body) });
const del: RequestInit = { method: "DELETE" };

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

/** Query keys for user-scoped data always include the user id, so sessions never share cache. */
export const queryKeys = {
  me: (u: string) => ["me", u] as const,
  usage: (u: string) => ["usage", u] as const,
  papers: (u: string, filters: object = {}) => ["papers", u, filters] as const,
  paper: (u: string, id: string) => ["paper", u, id] as const,
  collections: (u: string) => ["collections", u] as const,
  threads: (u: string, paperId?: string) => ["threads", u, paperId ?? "all"] as const,
  thread: (u: string, id: string) => ["thread", u, id] as const,
  notes: (u: string, paperId: string) => ["notes", u, paperId] as const,
  summary: (u: string, paperId: string, level: string) => ["summary", u, paperId, level] as const,
  glossary: (u: string, paperId: string) => ["glossary", u, paperId] as const,
  references: (u: string, paperId: string) => ["references", u, paperId] as const,
  citedBy: (u: string, paperId: string) => ["citedBy", u, paperId] as const,
  chunks: (u: string, paperId: string) => ["chunks", u, paperId] as const,
  comparisons: (u: string) => ["comparisons", u] as const,
  comparison: (u: string, id: string) => ["comparison", u, id] as const,
  due: (u: string) => ["due", u] as const,
  cards: (u: string, paperId: string) => ["cards", u, paperId] as const,
  reviews: (u: string) => ["reviews", u] as const,
  admin: (u: string) => ["admin", u] as const,
};

export type PaperFilters = { q?: string; collection_id?: string; starred?: boolean; status?: string };

export const api = {
  health: () => apiFetch<Health>("/health", {}, { auth: false }),
  me: () => apiFetch<Profile>("/v1/me"),
  updateMe: (p: ProfileUpdate) => apiFetch<Profile>("/v1/me", patch(p)),
  usage: () => apiFetch<Usage>("/v1/me/usage"),
  deleteMe: () => apiFetch<{ job_id: string }>("/v1/me", del),

  papers: (f: PaperFilters = {}) =>
    apiFetch<{ items: PaperCard[]; next_cursor: string | null }>(`/v1/papers${qs({ ...f, limit: 100 })}`),
  paper: (id: string) => apiFetch<Paper>(`/v1/papers/${id}`),
  updatePaper: (id: string, p: Partial<Pick<PaperCard, "starred" | "tags" | "collection_id" | "read_progress">>) =>
    apiFetch<Paper>(`/v1/papers/${id}`, patch(p)),
  deletePaper: (id: string) => apiFetch<void>(`/v1/papers/${id}`, del),
  importPaper: (source: "arxiv" | "doi" | "url", value: string, collection_id?: string | null) =>
    kicked(apiFetch<{ paper_id: string; job_id: string | null; status: string }>(
      "/v1/papers/import",
      json({ source, value, collection_id: collection_id || null }),
    )),
  upload: (file: File, collection_id?: string | null) => {
    const fd = new FormData();
    fd.append("file", file);
    if (collection_id) fd.append("collection_id", collection_id);
    return kicked(
      apiFetch<{ paper_id: string; job_id: string | null; status: string }>("/v1/papers/upload", {
        method: "POST",
        body: fd,
      }),
    );
  },
  paperFile: async (id: string) => (await rawFetch(`/v1/papers/${id}/file`)).arrayBuffer(),
  chunks: (id: string) => apiFetch<Chunk[]>(`/v1/papers/${id}/chunks`),
  references: (id: string) => apiFetch<Reference[]>(`/v1/papers/${id}/references`),
  citedBy: (id: string) =>
    apiFetch<{ title: string | null; authors: string[]; year: number | null; arxiv_id: string | null; doi: string | null }[]>(
      `/v1/papers/${id}/citations`,
    ),
  cite: (id: string, style: "bibtex" | "apa" | "ieee") => apiFetch<string>(`/v1/papers/${id}/bibtex?style=${style}`),
  job: (id: string) => {
    kickWorker();
    return apiFetch<Job>(`/v1/jobs/${id}`);
  },

  collections: () => apiFetch<Collection[]>("/v1/collections"),
  createCollection: (name: string) => apiFetch<Collection>("/v1/collections", json({ name })),
  renameCollection: (id: string, name: string) => apiFetch<Collection>(`/v1/collections/${id}`, patch({ name })),
  deleteCollection: (id: string) => apiFetch<void>(`/v1/collections/${id}`, del),

  threads: (paperId?: string) =>
    apiFetch<{ items: Thread[] }>(`/v1/threads${qs({ paper_id: paperId })}`).then((r) => r.items),
  thread: (id: string) => apiFetch<ThreadDetail>(`/v1/threads/${id}`),
  createThread: (scope: Thread["scope"]) => apiFetch<Thread>("/v1/threads", json({ scope })),
  deleteThread: (id: string) => apiFetch<void>(`/v1/threads/${id}`, del),
  feedback: (messageId: string, rating: 1 | -1) =>
    apiFetch<void>(`/v1/messages/${messageId}/feedback`, json({ rating })),
  saveNote: (messageId: string, paper_id: string) =>
    apiFetch<Note>(`/v1/messages/${messageId}/save-note`, json({ paper_id })),

  notes: (paperId: string) => apiFetch<Note[]>(`/v1/papers/${paperId}/notes`),
  createNote: (paperId: string, n: Pick<Note, "anchor" | "body_md" | "color">) =>
    apiFetch<Note>(`/v1/papers/${paperId}/notes`, json(n)),
  updateNote: (id: string, n: Partial<Pick<Note, "body_md" | "color">>) => apiFetch<Note>(`/v1/notes/${id}`, patch(n)),
  deleteNote: (id: string) => apiFetch<void>(`/v1/notes/${id}`, del),
  exportNotes: (paperId: string) => apiFetch<string>(`/v1/papers/${paperId}/notes/export?format=md`),

  summary: (paperId: string, level: Level) =>
    apiFetch<Summary>(`/v1/papers/${paperId}/summary${qs({ kind: "structured", level })}`),
  regenerateSummary: (paperId: string, level: Level) =>
    kicked(apiFetch<{ job_id: string }>(`/v1/papers/${paperId}/summary/regenerate${qs({ level })}`, { method: "POST" })),
  glossary: (paperId: string) =>
    apiFetch<{ terms: GlossaryTerm[] }>(`/v1/papers/${paperId}/summary${qs({ kind: "glossary" })}`),

  makeCards: (paperId: string, count: number) =>
    kicked(apiFetch<{ job_id: string }>(`/v1/papers/${paperId}/flashcards`, json({ count }))),
  cards: (paperId: string) => apiFetch<Flashcard[]>(`/v1/papers/${paperId}/flashcards`),
  due: () => apiFetch<Flashcard[]>("/v1/flashcards/due?limit=50"),
  reviewCard: (id: string, grade: number) => apiFetch<unknown>(`/v1/flashcards/${id}/review`, json({ grade })),

  comparisons: () => apiFetch<Comparison[]>("/v1/comparisons"),
  comparison: (id: string) => apiFetch<Comparison>(`/v1/comparisons/${id}`),
  createComparison: (paper_ids: string[], title?: string) =>
    kicked(apiFetch<{ comparison_id: string; job_id: string }>("/v1/comparisons", json({ paper_ids, title }))),
  addColumn: (id: string, label: string, question: string) =>
    kicked(apiFetch<{ job_id: string }>(`/v1/comparisons/${id}/columns`, json({ label, question }))),
  deleteComparison: (id: string) => apiFetch<void>(`/v1/comparisons/${id}`, del),

  discover: (q: string, yearFrom?: number, oaOnly = true) =>
    apiFetch<DiscoverResult[]>(`/v1/discover/search${qs({ q, year_from: yearFrom, open_access_only: oaOnly })}`),
  share: (kind: "summary" | "comparison", ref_id: string) =>
    apiFetch<{ share_id: string; url: string }>("/v1/share", json({ kind, ref_id })),
  publicShare: (id: string) => apiFetch<Record<string, unknown>>(`/v1/share/${id}`, {}, { auth: false }),

  startReview: (collectionId: string, topic: string, style: "apa" | "ieee", length: "short" | "long") =>
    kicked(apiFetch<{ job_id: string }>(`/v1/collections/${collectionId}/review`, json({ topic, style, length }))),
  reviews: () => apiFetch<ReviewItem[]>("/v1/reviews"),
  exportReview: (jobId: string, format: "md" | "tex" | "bib") =>
    apiFetch<string>(`/v1/exports/${jobId}?format=${format}`),

  adminMetrics: () => apiFetch<Record<string, unknown>>("/v1/admin/metrics"),
  adminJobs: () => apiFetch<Record<string, unknown>[]>("/v1/admin/jobs"),
  adminRetry: (id: string) => apiFetch<unknown>(`/v1/admin/jobs/${id}/retry`, { method: "POST" }),
};

/** Download text or bytes as a file in the browser. */
export function downloadFile(name: string, data: BlobPart, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadFromApi(path: string, name: string) {
  const res = await rawFetch(path);
  downloadFile(name, await res.blob(), res.headers.get("content-type") ?? "application/octet-stream");
}
