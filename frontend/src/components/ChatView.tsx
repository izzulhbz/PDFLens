import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import type {
  AskResponse,
  ModelChoice,
  PastMessage,
  PdfDocument,
  ProviderName,
  ProvidersResponse,
  SummaryOptions,
  SummaryResponse,
} from "../types";
import { AnswerMessage } from "./AnswerMessage";
import { chatTitle } from "./HistoryPanel";
import { FileIcon, SendIcon } from "./icons";
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
// twice in development, and the user may click between chats quickly:
// without this, both could start a (slow, paid) summary for the same file.
const summariesInFlight = new Map<number, Promise<SummaryResponse>>();

function loadSummary(
  documentId: number,
  model: ModelChoice,
  options: SummaryOptions,
): Promise<SummaryResponse> {
  let pending = summariesInFlight.get(documentId);
  if (!pending) {
    pending = api
      .getSummary(documentId)
      .then((saved) => saved ?? api.createSummary(documentId, model, options))
      .finally(() => summariesInFlight.delete(documentId));
    summariesInFlight.set(documentId, pending);
  }
  return pending;
}

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong.";
}

function toEntry({ question, ...answer }: PastMessage): ChatEntry {
  return { question, answer };
}

interface Props {
  document: PdfDocument;
  /** The chat so far, or undefined if it hasn't been loaded from the server yet. */
  history: ChatEntry[] | undefined;
  onHistoryChange: (entries: ChatEntry[]) => void;
  /** Which model answers, as chosen in the picker plus the user's default model. */
  model: ModelChoice;
  providers: ProvidersResponse | null;
  onProviderChange: (provider: ProviderName) => void;
  summaryOptions: SummaryOptions;
  /** Called with the summary's title, which becomes the chat's name. */
  onSummary: (documentId: number, title: string) => void;
  onError: (error: unknown) => void;
}

export function ChatView(props: Props) {
  const { document, history, onHistoryChange, model, summaryOptions, onSummary, onError } =
    props;
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [summary, setSummary] = useState<SummaryState>({ status: "loading" });
  const [regenerating, setRegenerating] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const ready = document.status === "ready";

  // Reopening a chat: load its earlier questions and answers.
  useEffect(() => {
    if (!ready || history !== undefined) return;
    let current = true;
    api.messages(document.id).then(
      (messages) => current && onHistoryChange(messages.map(toEntry)),
      (err: unknown) => {
        if (!current) return;
        onHistoryChange([]);
        onError(err);
      },
    );
    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document.id, ready]);

  // The summary comes first: load the saved one, or write it if there's none.
  useEffect(() => {
    if (!ready) return;
    let current = true;
    loadSummary(document.id, model, summaryOptions).then(
      (data) => {
        onSummary(document.id, data.summary.title);
        if (current) setSummary({ status: "ready", data });
      },
      (err: unknown) => {
        if (!current) return;
        if (err instanceof ApiError && err.status === 401) onError(err);
        else setSummary({ status: "error", message: errorMessage(err) });
      },
    );
    return () => {
      current = false;
    };
    // Only when the document changes: changing a setting shouldn't rewrite
    // the summary by itself (the card offers to regenerate instead).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [document.id, ready]);

  // Keep the newest message in view, as chat apps do.
  const entryCount = history?.length ?? 0;
  useEffect(() => {
    const element = scroller.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [entryCount, summary.status, asking]);

  async function regenerate() {
    setRegenerating(true);
    try {
      const data = await api.createSummary(document.id, model, summaryOptions);
      onSummary(document.id, data.summary.title);
      setSummary({ status: "ready", data });
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

    const before = history ?? [];
    setAsking(true);
    setQuestion("");
    onHistoryChange([...before, { question: text }]);
    try {
      const answer = await api.ask(document.id, text, model);
      onHistoryChange([...before, { question: text, answer }]);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onError(err);
        return;
      }
      onHistoryChange([...before, { question: text, error: errorMessage(err) }]);
    } finally {
      setAsking(false);
    }
  }

  // Questions open once the summary is shown, or once it has failed (a
  // broken summary shouldn't lock the user out of asking).
  const canAsk = ready && summary.status !== "loading";

  return (
    <section className="chat" aria-label={chatTitle(document)}>
      <header className="chat-header">
        <div className="chat-title">
          <h1>{chatTitle(document)}</h1>
          <span className="muted small">
            {document.filename}
            {document.page_count ? ` - ${document.page_count} pages` : ""}
          </span>
        </div>
        <ProviderSelect
          providers={props.providers}
          value={model.provider}
          onChange={props.onProviderChange}
          defaultModel={model.prefer}
        />
      </header>

      <div className="messages" ref={scroller} aria-live="polite">
        <div className="message user">
          <div className="bubble attachment">
            <FileIcon size={20} />
            <span>
              <span className="filename">{document.filename}</span>
              <span className="muted small">
                PDF{document.page_count ? `, ${document.page_count} pages` : ""}
              </span>
            </span>
          </div>
        </div>

        <div className="message assistant">
          {document.status === "processing" && (
            <p className="bubble muted" role="status">
              Reading your PDF... Its summary appears here when it's ready.
            </p>
          )}
          {document.status === "failed" && (
            <p className="bubble error" role="alert">
              This PDF couldn't be processed: {document.error_message ?? "unknown error"}
            </p>
          )}
          {ready && summary.status === "loading" && (
            <p className="bubble muted" role="status">
              Summarising this document... This can take a minute with a local model.
            </p>
          )}
          {ready && summary.status === "error" && (
            <div className="bubble">
              <p role="alert" className="error">
                Couldn't write a summary: {summary.message}
              </p>
              <button type="button" onClick={regenerate} disabled={regenerating}>
                {regenerating ? "Trying again..." : "Try again"}
              </button>
            </div>
          )}
          {ready && summary.status === "ready" && (
            <SummaryCard
              data={summary.data}
              currentOptions={summaryOptions}
              onRegenerate={regenerate}
              regenerating={regenerating}
            />
          )}
        </div>

        {canAsk && history?.length === 0 && (
          <p className="muted center-text">
            Ask anything about this document. Answers cite the pages they come from.
          </p>
        )}
        {(history ?? []).map((entry, i) => (
          <div key={i} className="exchange">
            <div className="message user">
              <p className="bubble">{entry.question}</p>
            </div>
            <div className="message assistant">
              {entry.answer && <AnswerMessage answer={entry.answer} />}
              {entry.error && (
                <p role="alert" className="bubble error">
                  {entry.error}
                </p>
              )}
              {!entry.answer && !entry.error && <p className="bubble muted">Thinking...</p>}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="composer">
        <textarea
          aria-label="Your question"
          placeholder={
            canAsk
              ? "Ask a question about this PDF..."
              : ready
                ? "Questions open after the summary..."
                : "Questions open once the PDF is ready..."
          }
          maxLength={MAX_QUESTION_LENGTH}
          rows={1}
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
        <button
          type="submit"
          className="send"
          aria-label={asking ? "Asking..." : "Ask"}
          disabled={!canAsk || asking || !question.trim()}
        >
          <SendIcon />
        </button>
      </form>
      <p className="composer-hint muted small">
        Answers come only from this PDF and can still be wrong. Check the cited pages.
      </p>
    </section>
  );
}
