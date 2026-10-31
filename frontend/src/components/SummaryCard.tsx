import type { SummaryResponse } from "../types";
import { PROVIDER_LABELS } from "./ProviderSelect";

function pagesLabel(pages: number[]): string {
  if (pages.length === 0) return "";
  const first = pages[0]!;
  const last = pages[pages.length - 1]!;
  if (first === last) return `p. ${first}`;
  // Consecutive pages read better as a range.
  return last - first === pages.length - 1 ? `pp. ${first}-${last}` : `pp. ${pages.join(", ")}`;
}

interface Props {
  data: SummaryResponse;
  onRegenerate: () => void;
  regenerating: boolean;
}

/**
 * A document's study summary, laid out as sections. Everything comes from
 * structured JSON and is rendered as plain text: no Markdown or HTML from
 * the model is ever interpreted.
 */
export function SummaryCard({ data, onRegenerate, regenerating }: Props) {
  const { summary } = data;
  const provider = data.provider ? (PROVIDER_LABELS[data.provider] ?? data.provider) : null;

  return (
    <details className="summary" open>
      <summary>Document summary</summary>
      <h3>{summary.title}</h3>
      <p className="overview">{summary.overview}</p>

      <section>
        <h4>What it covers</h4>
        <ol className="topics">
          {summary.topics.map((topic, i) => (
            <li key={i}>
              <span className="topic-name">{topic.name}</span>
              {topic.pages.length > 0 && <span className="pages">{pagesLabel(topic.pages)}</span>}
              {topic.summary && <p>{topic.summary}</p>}
            </li>
          ))}
        </ol>
      </section>

      {summary.learning_outcomes.length > 0 && (
        <section>
          <h4>What you'll learn</h4>
          <ul className="outcomes">
            {summary.learning_outcomes.map((outcome, i) => (
              <li key={i}>{outcome}</li>
            ))}
          </ul>
        </section>
      )}

      {summary.key_terms.length > 0 && (
        <section>
          <h4>Key terms</h4>
          <dl className="terms">
            {summary.key_terms.map((item, i) => (
              <div key={i}>
                <dt>{item.term}</dt>
                <dd>{item.definition}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      <p className="meta">
        {provider ? `Summary by ${provider}. ` : ""}
        Generated from the document only; check the cited pages for details.{" "}
        <button type="button" className="link" onClick={onRegenerate} disabled={regenerating}>
          {regenerating ? "Regenerating..." : "Regenerate"}
        </button>
      </p>
    </details>
  );
}
