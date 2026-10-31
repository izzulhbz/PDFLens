// Shapes of the JSON the backend returns (see the API table in the README).

export interface User {
  id: number;
  email: string;
}

export type DocumentStatus = "processing" | "ready" | "failed";

export interface PdfDocument {
  id: number;
  filename: string;
  page_count: number | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
}

export const PROVIDER_NAMES = ["auto", "anthropic", "ollama"] as const;
export type ProviderName = (typeof PROVIDER_NAMES)[number];

export interface ProviderInfo {
  name: ProviderName;
  model: string | null;
  available: boolean;
  detail: string;
}

export interface ProvidersResponse {
  default: ProviderName;
  providers: ProviderInfo[];
}

export interface Source {
  chunk_id: number;
  page_start: number;
  page_end: number;
  snippet: string;
  cited: boolean;
}

export interface SummaryTopic {
  name: string;
  summary: string;
  pages: number[];
}

export interface Summary {
  title: string;
  overview: string;
  topics: SummaryTopic[];
  learning_outcomes: string[];
  key_terms: { term: string; definition: string }[];
}

export interface SummaryResponse {
  summary: Summary;
  provider: string | null;
  created_at: string | null;
}

export interface AskResponse {
  answer: string;
  provider: string | null;
  refused: boolean;
  latency_ms: number;
  sources: Source[];
}
