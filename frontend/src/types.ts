// Shapes of the JSON the backend returns (see the API table in the README).

export interface User {
  id: number;
  email: string;
}

export type DocumentStatus = "processing" | "ready" | "failed";

export interface PdfDocument {
  id: number;
  /** What the document is about, from its summary. null until it has one. */
  title: string | null;
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

export interface ChartPoint {
  label: string;
  value: number;
}

export interface SummaryChart {
  title: string;
  kind: "bar" | "line";
  x_label: string;
  y_label: string;
  points: ChartPoint[];
  pages: number[];
}

export interface Summary {
  title: string;
  overview: string;
  topics: SummaryTopic[];
  learning_outcomes: string[];
  key_terms: { term: string; definition: string }[];
  /** Present only when charts were asked for; empty if the PDF had no chartable data. */
  charts?: SummaryChart[];
}

export const TONES = ["professional", "simple", "friendly", "academic"] as const;
export type Tone = (typeof TONES)[number];
export const SUMMARY_LENGTHS = ["brief", "standard", "detailed"] as const;
export type SummaryLength = (typeof SUMMARY_LENGTHS)[number];

/** How a summary is written. The backend accepts only these values. */
export interface SummaryOptions {
  tone: Tone;
  length: SummaryLength;
  include_charts: boolean;
}

export interface SummaryResponse {
  summary: Summary;
  /** The settings it was written with; null for summaries from before settings existed. */
  options: SummaryOptions | null;
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

/** A question and answer from earlier in a chat, as GET /api/documents/<id>/messages returns it. */
export interface PastMessage extends AskResponse {
  question: string;
  asked_at: string;
}
