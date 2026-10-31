import { useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import type {
  AskResponse,
  PdfDocument,
  ProviderName,
  ProvidersResponse,
  SummaryResponse,
} from "../types";
import { AnswerMessage } from "./AnswerMessage";
import { ProviderSelect } from "./ProviderSelect";
import { SummaryCard } from "./SummaryCard";

const MAX_QUESTION_LENGTH = 2000; // matches the backend

export interface ChatEntry {
  question: string;
  answer?: AskResponse;
  error?: string;
}

type SummaryState =
  | { status: "loading" }
  | { status: "ready"; data: SummaryResponse }
  | { status: "error"; message: string };

// One summary request per document at a time. React StrictMode runs effects
// twice in development, and the user may click between documents quickly:
// without this, both could start a (slow, paid) summary for the same file.
const summariesInFlight = new Map<number, Promise<SummaryResponse>>();

function loadSummary(documentId: number, provider: ProviderName): Promise<SummaryResponse> {
  let pending = summariesInFlight.get(documentId);
  if (!pending) {
    pending = api
      .getSummary(documentId)
      .then((saved) => saved ?? api.createSummary(documentId, provider))
      .finally(() => summariesInFlight.delete(documentId));
    summariesInFlight.set(documentId, pending);
  }
  return pending;
}

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

interface Props {
  document: PdfDocument;
  history: ChatEntry[];
  onHistoryChange: (entries: ChatEntry[]) => void;
  providers: ProvidersResponse | null;
  provider: ProviderName;
  onProviderChange: (provider: ProviderName) => void;
  onError: (error: unknown) => void;
}

export function ChatView(props: Props) {
  const { document, history, onHistoryChange, providers, provider, onError } = props;
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [summary, setSummary] = useState<SummaryState>({ status: "loading" });
  const [regenerating, setRegenerating] = useState(false);
  const ready = document.status === "ready";

  // The summary comes first: load the saved one, or write it if there's none.
  useEffect(() => {
    if (!ready) return;
    let current = true;
    loadSummary(document.id, provider).then(
      (data) => current && setSummary({ status: "ready", data }),
      (err: unknown) => {
        if (!current) return;
        if (err instanceof ApiError && err.status === 401) onError(err);
        else setSummary({ status: "error", message: errorMessage(err) });
      },
    );
    return () => {
      current = false;
    };
    // Only when the document changes: switching provider shouldn't rewrite it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document.id, ready]);

  async function regenerate() {
    setRegenerating(true);
    try {
      setSummary({ status: "ready", data: await api.createSummary(document.id, provider) });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) onError(err);
      else setSummary({ status: "error", message: errorMessage(err) });
    } finally {
      setRegenerating(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || asking) return;

    setAsking(true);
    setQuestion("");
    onHistoryChange([...history, { question: text }]);
    try {
      const answer = await api.ask(document.id, text, provider);
      onHistoryChange([...history, { question: text, answer }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onError(err);
        return;
      }
      onHistoryChange([...history, { question: text, error: errorMessage(err) }]);
    } finally {
      setAsking(false);
    }
  }

  if (!ready) {
    return (
      <section className="chat empty">
        <h2>{document.filename}</h2>
        <p className="muted">
          {document.status === "processing"
            ? "This document is still being processed. Its summary appears when it's ready."
            : `This document couldn't be processed: ${document.error_message ?? "unknown error"}`}
        </p>
      </section>
    );
  }

  // Questions open once the summary is shown, or once it has failed (a
  // broken summary shouldn't lock the user out of asking).
  const canAsk = summary.status !== "loading";

  return (
    <section className="chat">
      <header className="chat-header">
        <h2>{document.filename}</h2>
        <ProviderSelect providers={providers} value={provider} onChange={props.onProviderChange} />
      </header>

      {summary.status === "loading" && (
        <div className="summary loading" role="status">
          Summarising this document... This can take a minute with a local model.
        </div>
      )}
      {summary.status === "error" && (
        <div className="summary failed">
          <p role="alert" className="error">
            Couldn't write a summary: {summary.message}
          </p>
          <button type="button" onClick={regenerate} disabled={regenerating}>
            {regenerating ? "Trying again..." : "Try again"}
          </button>
        </div>
      )}
      {summary.status === "ready" && (
        <SummaryCard data={summary.data} onRegenerate={regenerate} regenerating={regenerating} />
      )}

      {canAsk && (
        <ol className="messages" aria-live="polite">
          {history.length === 0 && (
            <li className="muted">Now ask anything about this document. Answers cite their pages.</li>
          )}
          {history.map((entry, i) => (
            <li key={i}>
              <p className="question">{entry.question}</p>
              {entry.answer && <AnswerMessage answer={entry.answer} />}
              {entry.error && (
                <p role="alert" className="error">
                  {entry.error}
                </p>
              )}
              {!entry.answer && !entry.error && <p className="muted">Thinking...</p>}
            </li>
          ))}
        </ol>
      )}

      <form onSubmit={submit} className="ask">
        <textarea
          aria-label="Your question"
          placeholder={canAsk ? "e.g. What does HNSW build?" : "Questions open after the summary..."}
          maxLength={MAX_QUESTION_LENGTH}
          value={question}
          disabled={!canAsk}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button type="submit" disabled={!canAsk || asking || !question.trim()}>
          {asking ? "Asking..." : "Ask"}
        </button>
      </form>
    </section>
  );
}
