import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { defaultOptions, summary } from "../test/fixtures";
import type { SummaryResponse } from "../types";
import { SummaryCard } from "./SummaryCard";

function renderCard(data: SummaryResponse = summary, onRegenerate = () => {}) {
  return render(
    <SummaryCard
      data={data}
      currentOptions={defaultOptions}
      onRegenerate={onRegenerate}
      regenerating={false}
    />,
  );
}

describe("SummaryCard", () => {
  it("lays the summary out as titled sections", () => {
    renderCard();

    expect(screen.getByRole("heading", { name: "Retrieval-Augmented Generation" })).toBeTruthy();
    expect(screen.getByText(/How RAG answers questions/)).toBeTruthy();

    const covers = screen.getByRole("heading", { name: "What it covers" }).parentElement!;
    const topics = within(covers).getAllByRole("listitem");
    expect(topics.map((t) => t.textContent)).toEqual([
      "Embeddingsp. 2Vectors that capture meaning.",
      "HNSWpp. 3-4A layered graph for fast search.",
    ]);

    expect(screen.getByRole("heading", { name: "What you'll learn" })).toBeTruthy();
    expect(screen.getByText("Explain how retrieval grounds an answer")).toBeTruthy();
    expect(screen.getByText("Chunk").tagName).toBe("DT");
    expect(screen.getByText(/Summary by Ollama/)).toBeTruthy();
  });

  it("leaves out sections the model returned empty", () => {
    const sparse = {
      ...summary,
      summary: { ...summary.summary, learning_outcomes: [], key_terms: [] },
    };

    renderCard(sparse);

    expect(screen.queryByRole("heading", { name: "Key terms" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "What you'll learn" })).toBeNull();
  });

  it("renders model output as text, never as HTML", () => {
    const hostile = {
      ...summary,
      summary: { ...summary.summary, overview: "<script>alert(1)</script> **bold**" },
    };

    const { container } = renderCard(hostile);

    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script> **bold**");
  });

  it("offers to regenerate", async () => {
    const onRegenerate = vi.fn();
    renderCard(summary, onRegenerate);

    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(onRegenerate).toHaveBeenCalled();
  });

  it("draws the document's charts, or says there was nothing to chart", () => {
    const chart = {
      title: "Enrolment by year",
      kind: "bar" as const,
      x_label: "Year",
      y_label: "Students",
      points: [
        { label: "2021", value: 1200 },
        { label: "2022", value: 1350 },
      ],
      pages: [4],
    };
    const { unmount } = renderCard({ ...summary, summary: { ...summary.summary, charts: [chart] } });

    expect(screen.getByRole("heading", { name: "Data from the document" })).toBeTruthy();
    expect(screen.getByRole("img", { name: /Enrolment by year/ })).toBeTruthy();
    unmount();

    renderCard(); // charts were asked for, but the PDF had none
    expect(screen.getByText(/No charts/)).toBeTruthy();
  });

  it("offers to regenerate when it was written with different settings", async () => {
    const onRegenerate = vi.fn();
    renderCard({ ...summary, options: { ...defaultOptions, tone: "simple" } }, onRegenerate);

    await userEvent.click(screen.getByRole("button", { name: "Regenerate with current settings" }));

    expect(onRegenerate).toHaveBeenCalled();
  });

  it("says nothing about settings when they match", () => {
    renderCard();

    expect(screen.queryByText(/different settings/)).toBeNull();
    expect(screen.getByText(/standard, professional tone/)).toBeTruthy();
  });
});
