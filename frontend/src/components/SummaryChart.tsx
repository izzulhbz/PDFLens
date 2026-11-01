// A bar or line chart of numbers taken from the PDF, drawn as plain SVG
// (no chart library). The backend only sends charts whose every value
// appears on the pages the chart cites; the "Show data" table and the page
// chip let the reader check them.
//
// Everything is rendered as text and SVG attributes: labels come from an
// LLM that read untrusted PDF text, so nothing is ever interpreted as HTML.

import { useState } from "react";

import { pagesLabel } from "../pages";
import type { SummaryChart as Chart } from "../types";

// Drawing size in SVG units. The SVG scales to the width of its container.
const WIDTH = 560;
const HEIGHT = 260;
const MARGIN = { top: 16, right: 16, bottom: 44, left: 56 };
const PLOT_W = WIDTH - MARGIN.left - MARGIN.right;
const PLOT_H = HEIGHT - MARGIN.top - MARGIN.bottom;
const CHAR_WIDTH = 6.5; // rough width of one 11px label character

const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const tickFormat = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

/** A "nice" step (1, 2, 2.5 or 5 times a power of ten) for about `count` ticks. */
function niceStep(range: number, count: number): number {
  const rough = range / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const multiple = [1, 2, 2.5, 5, 10].find((m) => m * power >= rough) ?? 10;
  return multiple * power;
}

/** Y-axis ticks covering [low, high], starting and ending on round numbers. */
export function niceTicks(low: number, high: number, count = 4): number[] {
  if (low === high) {
    // A flat series: give it some room above and below.
    const pad = Math.abs(low) || 1;
    [low, high] = [low - pad, high + pad];
  }
  const step = niceStep(high - low, count);
  const ticks = [];
  for (let t = Math.floor(low / step) * step; t <= high + step / 2; t += step) {
    ticks.push(Number(t.toPrecision(12))); // avoid 0.30000000000000004
  }
  if (ticks[ticks.length - 1]! < high) ticks.push(ticks[ticks.length - 1]! + step);
  return ticks;
}

function truncate(text: string, maxChars: number): string {
  return text.length <= maxChars ? text : `${text.slice(0, Math.max(1, maxChars - 3))}...`;
}

/** A bar with 4px rounded corners at its value end, square at the baseline. */
function barPath(x: number, width: number, base: number, end: number): string {
  const height = Math.abs(base - end);
  const r = Math.min(4, width / 2, height);
  if (end <= base) {
    // Positive value: the bar grows upwards from the baseline.
    return `M${x},${base}V${end + r}Q${x},${end} ${x + r},${end}H${x + width - r}Q${x + width},${end} ${x + width},${end + r}V${base}Z`;
  }
  return `M${x},${base}V${end - r}Q${x},${end} ${x + r},${end}H${x + width - r}Q${x + width},${end} ${x + width},${end - r}V${base}Z`;
}

export function SummaryChart({ chart }: { chart: Chart }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const values = chart.points.map((p) => p.value);
  // Bars must start at zero, or their lengths would lie. Lines needn't.
  const low = chart.kind === "bar" ? Math.min(0, ...values) : Math.min(...values);
  const high = chart.kind === "bar" ? Math.max(0, ...values) : Math.max(...values);
  const ticks = niceTicks(low, high);
  const yMin = ticks[0]!;
  const yMax = ticks[ticks.length - 1]!;
  const y = (value: number) => MARGIN.top + PLOT_H - ((value - yMin) / (yMax - yMin)) * PLOT_H;

  const column = PLOT_W / chart.points.length;
  const centre = (i: number) => MARGIN.left + column * (i + 0.5);
  const barWidth = Math.min(48, column * 0.6);
  // Show every label if there's room; otherwise every other one.
  const labelEvery = column < 32 ? 2 : 1;
  const maxChars = Math.floor((column * labelEvery) / CHAR_WIDTH);
  const baseline = y(Math.max(yMin, Math.min(0, yMax)));

  const active = hovered === null ? null : chart.points[hovered]!;
  const tooltipText = active ? `${active.label}: ${numberFormat.format(active.value)}` : "";
  const tooltipW = tooltipText.length * 7 + 16;
  const tooltipX =
    hovered === null
      ? 0
      : Math.min(Math.max(centre(hovered) - tooltipW / 2, 0), WIDTH - tooltipW);
  const tooltipY = active ? Math.max(y(active.value) - 36, 0) : 0;

  return (
    <figure className="chart">
      <figcaption>
        <span className="chart-title">{chart.title}</span>
        {chart.pages.length > 0 && <span className="pages">{pagesLabel(chart.pages)}</span>}
      </figcaption>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${chart.kind === "bar" ? "Bar" : "Line"} chart: ${chart.title}. The values are in the table below.`}
        onMouseLeave={() => setHovered(null)}
      >
        {/* Recessive grid and y-axis ticks */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="chart-grid" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={y(tick)} y2={y(tick)} />
            <text className="chart-tick" x={MARGIN.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle">
              {tickFormat.format(tick)}
            </text>
          </g>
        ))}
        <line className="chart-axis" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={baseline} y2={baseline} />

        {chart.points.map((point, i) =>
          i % labelEvery === 0 ? (
            <text key={i} className="chart-tick" x={centre(i)} y={HEIGHT - MARGIN.bottom + 18} textAnchor="middle">
              {truncate(point.label, maxChars)}
            </text>
          ) : null,
        )}
        {chart.x_label && (
          <text className="chart-axis-label" x={MARGIN.left + PLOT_W / 2} y={HEIGHT - 6} textAnchor="middle">
            {chart.x_label}
          </text>
        )}
        {chart.y_label && (
          <text
            className="chart-axis-label"
            transform={`translate(14 ${MARGIN.top + PLOT_H / 2}) rotate(-90)`}
            textAnchor="middle"
          >
            {chart.y_label}
          </text>
        )}

        {hovered !== null && chart.kind === "line" && (
          <line className="chart-crosshair" x1={centre(hovered)} x2={centre(hovered)} y1={MARGIN.top} y2={MARGIN.top + PLOT_H} />
        )}

        {chart.kind === "bar" ? (
          chart.points.map((point, i) => (
            <path
              key={i}
              className={`chart-bar ${hovered !== null && hovered !== i ? "dimmed" : ""}`}
              d={barPath(centre(i) - barWidth / 2, barWidth, baseline, y(point.value))}
            />
          ))
        ) : (
          <>
            <polyline
              className="chart-line"
              points={chart.points.map((p, i) => `${centre(i)},${y(p.value)}`).join(" ")}
            />
            {chart.points.map((point, i) => (
              <circle key={i} className="chart-marker" cx={centre(i)} cy={y(point.value)} r={hovered === i ? 5 : 4} />
            ))}
          </>
        )}

        {/* Hover targets: whole columns, much bigger than the marks themselves. */}
        {chart.points.map((point, i) => (
          <rect
            key={i}
            className="chart-hit"
            x={MARGIN.left + column * i}
            y={MARGIN.top}
            width={column}
            height={PLOT_H}
            onMouseEnter={() => setHovered(i)}
          >
            <title>{`${point.label}: ${numberFormat.format(point.value)}`}</title>
          </rect>
        ))}

        {active && (
          <g className="chart-tooltip" pointerEvents="none">
            <rect x={tooltipX} y={tooltipY} width={tooltipW} height={26} rx={6} />
            <text x={tooltipX + 8} y={tooltipY + 17}>
              {tooltipText}
            </text>
          </g>
        )}
      </svg>

      <details className="chart-data">
        <summary>Show data</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">{chart.x_label || "Label"}</th>
              <th scope="col">{chart.y_label || "Value"}</th>
            </tr>
          </thead>
          <tbody>
            {chart.points.map((point, i) => (
              <tr key={i}>
                <td>{point.label}</td>
                <td>{numberFormat.format(point.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
