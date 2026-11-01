import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";
import { jsonResponse } from "./test/fixtures";

describe("api client", () => {
  it("sends the CSRF header and the session cookie with every request", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ user: { id: 1, email: "a@b.com" } }));

    await api.login("a@b.com", "correct horse battery");

    const [path, init] = fetchMock.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    expect(path).toBe("/api/auth/login");
    expect(headers.get("X-PDFLens-CSRF")).toBe("1");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.credentials).toBe("same-origin");
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "a@b.com",
      password: "correct horse battery",
    });
  });

  it("sends the chosen model and the default model with a question", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}));

    await api.ask(7, "What is HNSW?", { provider: "auto", prefer: "ollama_gpu" });

    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({
      document_id: 7,
      question: "What is HNSW?",
      provider: "auto",
      prefer: "ollama_gpu",
    });
  });

  it("uploads as multipart form data without setting Content-Type itself", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ document: { id: 1 } }, 202));

    await api.upload(new File(["%PDF-1.7"], "notes.pdf", { type: "application/pdf" }));

    const init = fetchMock.mock.calls[0]![1];
    expect(init?.body).toBeInstanceOf(FormData);
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  it("turns error responses into ApiError with the server's message", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ error: { code: "invalid_credentials", message: "Invalid email or password." } }, 401),
    );

    const error = await api.login("a@b.com", "wrong").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 401, code: "invalid_credentials", message: "Invalid email or password." });
  });

  it("reports a network failure clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(api.me()).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});
