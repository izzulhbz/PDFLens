import { pagesLabel } from "../pages";
import { sameSummaryOptions } from "../settings";
import type { SummaryOptions, SummaryResponse } from "../types";
import { PROVIDER_LABELS } from "./ProviderSelect";
import { SummaryChart } from "./SummaryChart";

interface Props {
  data: SummaryResponse;
  /** The user's current summary settings, to notice when this summary predates them. */
  currentOptions: SummaryOptions;
  onRegenerate: () => void;
  regenerating: boolean;
}

/**
 * A document's study summary, laid out as sections. Everything comes from
 * structured JSON and is rendered as plain text: no Markdown or HTML from
 * the model is ever interpreted.
 */
export function SummaryCard({ data, currentOptions, onRegenerate, regenerating }: Props) {
  const { summary, options } = data;
  const provider = data.provider ? (PROVIDER_LABELS[data.provider] ?? data.provider) : null;
  const outdated = !sameSummaryOptions(options, currentOptions);
  const charts = summary.charts ?? [];

  return (
    <details className="summary" open>
      <summary>
        Summary
        {options ? ` - ${options.length}, ${options.tone} tone` : ""}
      </summary>
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

      {charts.length > 0 && (
        <section>
          <h4>Data from the document</h4>
          {charts.map((chart, i) => (
            <SummaryChart key={i} chart={chart} />
          ))}
        </section>
      )}
      {summary.charts && charts.length === 0 && (
        <p className="hint">No charts: no numeric data in the pages read could be plotted and checked.</p>
      )}

      {outdated && (
        <p className="notice">
          This summary was written with different settings than your current ones.{" "}
          <button type="button" className="link" onClick={onRegenerate} disabled={regenerating}>
            Regenerate with current settings
          </button>
        </p>
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
