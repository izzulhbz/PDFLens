import type {
  AskResponse,
  PdfDocument,
  ProvidersResponse,
  SummaryOptions,
  SummaryResponse,
} from "../types";

/** The default settings, as the backend records them. */
export const defaultOptions: SummaryOptions = {
  tone: "professional",
  length: "standard",
  include_charts: true,
};

export const summary: SummaryResponse = {
  options: defaultOptions,
  provider: "ollama",
  created_at: "2026-11-01T10:05:00+00:00",
  summary: {
    title: "Retrieval-Augmented Generation",
    overview: "How RAG answers questions from documents a model never saw.",
    topics: [
      { name: "Embeddings", summary: "Vectors that capture meaning.", pages: [2] },
      { name: "HNSW", summary: "A layered graph for fast search.", pages: [3, 4] },
    ],
    learning_outcomes: ["Explain how retrieval grounds an answer"],
    key_terms: [{ term: "Chunk", definition: "A passage of a few hundred tokens." }],
    charts: [],
  },
};

export const readyDocument: PdfDocument = {
  id: 7,
  title: null,
  filename: "Week 7.pdf",
  page_count: 4,
  status: "ready",
  error_message: null,
  created_at: "2026-11-01T10:00:00+00:00",
};

export const providers: ProvidersResponse = {
  default: "auto",
  providers: [
    { name: "anthropic", model: "claude-haiku-5-5", available: false, detail: "No API key configured" },
    { name: "ollama", model: "llama3.2", available: true, detail: "Reachable" },
    { name: "auto", model: null, available: true, detail: "Ollama only" },
  ],
};

export const answer: AskResponse = {
  answer: "HNSW builds a layered graph [p. 3] and walks it greedily [pp. 3-4].",
  provider: "ollama",
  refused: false,
  latency_ms: 2200,
  sources: [
    { chunk_id: 11, page_start: 3, page_end: 3, snippet: "HNSW builds a layered graph...", cited: true },
    { chunk_id: 12, page_start: 1, page_end: 1, snippet: "Course introduction...", cited: false },
  ],
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
