// The only place that talks to the backend.
//
// - Every request carries the X-PDFLens-CSRF header, which the backend
//   requires on state-changing requests (its CSRF defence).
// - credentials: "same-origin" sends the HttpOnly session cookie. The
//   cookie itself is invisible to this code, so an XSS bug couldn't read it.
// - Errors become ApiError with the server's user-safe message.

import type {
  AskResponse,
  ModelChoice,
  PastMessage,
  PdfDocument,
  ProvidersResponse,
  SummaryOptions,
  SummaryResponse,
  User,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-PDFLens-CSRF", "1");

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Is it running?");
  }

  if (response.status === 204) {
    return undefined as T;
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed (HTTP ${response.status}).`,
    );
  }
  return body as T;
}

function postJson<T>(path: string, data: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export const api = {
  me: () => request<{ user: User }>("/api/auth/me").then((r) => r.user),
  login: (email: string, password: string) =>
    postJson<{ user: User }>("/api/auth/login", { email, password }).then((r) => r.user),
  register: (email: string, password: string) =>
    postJson<{ user: User }>("/api/auth/register", { email, password }).then((r) => r.user),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),

  listDocuments: () =>
    request<{ documents: PdfDocument[] }>("/api/documents").then((r) => r.documents),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    // No Content-Type header: the browser sets multipart/form-data with its boundary.
    return request<{ document: PdfDocument }>("/api/documents", {
      method: "POST",
      body: form,
    }).then((r) => r.document);
  },
  deleteDocument: (documentId: number) =>
    request<void>(`/api/documents/${documentId}`, { method: "DELETE" }),
  /** The questions already asked about a document, oldest first. */
  messages: (documentId: number) =>
    request<{ messages: PastMessage[] }>(`/api/documents/${documentId}/messages`).then(
      (r) => r.messages,
    ),

  /** The saved summary, or null if none has been written yet. */
  getSummary: (documentId: number) =>
    request<SummaryResponse>(`/api/documents/${documentId}/summary`).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 404 && err.code === "summary_not_found") {
        return null;
      }
      throw err;
    }),
  createSummary: (documentId: number, model: ModelChoice, options: SummaryOptions) =>
    postJson<SummaryResponse>(`/api/documents/${documentId}/summary`, { ...model, ...options }),

  providers: () => request<ProvidersResponse>("/api/providers"),
  ask: (documentId: number, question: string, model: ModelChoice) =>
    postJson<AskResponse>("/api/ask", { document_id: documentId, question, ...model }),
};
