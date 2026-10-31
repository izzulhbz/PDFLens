import { useState } from "react";

import type { AskResponse, Source } from "../types";
import { PROVIDER_LABELS } from "./ProviderSelect";

// Matches citations like [p. 4] and [pp. 4-5] (hyphen or en dash).
const EN_DASH = String.fromCharCode(0x2013);
const CITATION = new RegExp(`\\[(?:pp?\\.)\\s*(\\d+)(?:\\s*[-${EN_DASH}]\\s*(\\d+))?\\]`, "g");

type Part = { text: string } | { text: string; first: number; last: number };

/** Split an answer into plain text and citation parts. */
export function splitCitations(answer: string): Part[] {
  const parts: Part[] = [];
  let index = 0;
  for (const match of answer.matchAll(CITATION)) {
    const start = match.index ?? 0;
    if (start > index) parts.push({ text: answer.slice(index, start) });
    const first = Number(match[1]);
    parts.push({ text: match[0], first, last: match[2] ? Number(match[2]) : first });
    index = start + match[0].length;
  }
  if (index < answer.length) parts.push({ text: answer.slice(index) });
  return parts;
}

function overlaps(source: Source, first: number, last: number): boolean {
  return source.page_start <= last && first <= source.page_end;
}

function pagesLabel(source: Source): string {
  return source.page_start === source.page_end
    ? `Page ${source.page_start}`
    : `Pages ${source.page_start}-${source.page_end}`;
}

interface Props {
  answer: AskResponse;
}

export function AnswerMessage({ answer }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function toggle(chunkId: number) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(chunkId)) next.delete(chunkId);
      else next.add(chunkId);
      return next;
    });
  }

  function showCitation(first: number, last: number) {
    const matching = answer.sources.filter((s) => overlaps(s, first, last));
    setExpanded((current) => new Set([...current, ...matching.map((s) => s.chunk_id)]));
    const firstMatch = matching[0];
    if (firstMatch) {
      document.getElementById(`source-${firstMatch.chunk_id}`)?.scrollIntoView?.({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }

  const provider = answer.provider ? (PROVIDER_LABELS[answer.provider] ?? answer.provider) : null;

  return (
    <div className={`answer ${answer.refused ? "refused" : ""}`}>
      {/* Rendered as text only: the answer comes from an LLM that read untrusted PDF text. */}
      <p>
        {splitCitations(answer.answer).map((part, i) =>
          "first" in part ? (
            <button
              key={i}
              type="button"
              className="citation"
              onClick={() => showCitation(part.first, part.last)}
              aria-label={`Show source for ${part.text}`}
            >
              {part.text}
            </button>
          ) : (
            <span key={i}>{part.text}</span>
          ),
        )}
      </p>
      <p className="meta">
        {answer.refused ? "Not found in the document" : "Answer"}
        {provider ? ` - by ${provider}` : ""} - {(answer.latency_ms / 1000).toFixed(1)} s
      </p>

      {answer.sources.length > 0 && (
        <ul className="sources" aria-label="Sources">
          {answer.sources.map((source) => {
            const open = expanded.has(source.chunk_id);
            return (
              <li key={source.chunk_id} id={`source-${source.chunk_id}`}>
                <button
                  type="button"
                  className={`source ${source.cited ? "cited" : ""}`}
                  aria-expanded={open}
                  onClick={() => toggle(source.chunk_id)}
                >
                  {pagesLabel(source)}
                  {source.cited ? " - cited" : ""}
                </button>
                {open && <blockquote>{source.snippet}</blockquote>}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
