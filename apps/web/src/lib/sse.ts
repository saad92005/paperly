import { env } from "@/lib/env";
import { authHeaders, toApiError } from "@/lib/api";

export type SseEvent = { event: string; data: Record<string, unknown> };

/** POST (or GET) to an SSE endpoint and yield parsed events as they arrive. */
export async function* streamSse(
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const headers = await authHeaders(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  headers.set("Accept", "text/event-stream");
  const res = await fetch(`${env.apiBaseUrl}${path}`, { ...init, headers, signal });
  if (!res.ok) throw await toApiError(res);
  if (!res.body) return;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (!data.length) continue;
      try {
        yield { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
      } catch {
        // ignore malformed frames
      }
    }
  }
}
