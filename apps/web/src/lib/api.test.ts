import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/lib/api";

vi.mock("@/lib/session", () => ({ apiToken: async () => "test-token" }));

afterEach(() => vi.unstubAllGlobals());

describe("apiFetch", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ status: "ok" }), { status: 200, headers: { "content-type": "application/json" } })),
    );
    await expect(apiFetch<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
  });

  it("sends the API token as a Bearer header", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(
      async () => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/v1/me");
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("maps the API error shape to ApiError", async () => {
    const body = { error: { code: "unauthorized", message: "Sign in to continue.", request_id: "req_1" } };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 401 })));
    const err = await apiFetch("/v1/me").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 401, code: "unauthorized", requestId: "req_1" });
  });

  it("turns network failures into a friendly error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(apiFetch("/health")).rejects.toMatchObject({ code: "network", status: 0 });
  });
});
