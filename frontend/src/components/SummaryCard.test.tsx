import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { summary } from "../test/fixtures";
import { SummaryCard } from "./SummaryCard";

describe("SummaryCard", () => {
  it("lays the summary out as titled sections", () => {
    render(<SummaryCard data={summary} onRegenerate={() => {}} regenerating={false} />);

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

    render(<SummaryCard data={sparse} onRegenerate={() => {}} regenerating={false} />);

    expect(screen.queryByRole("heading", { name: "Key terms" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "What you'll learn" })).toBeNull();
  });

  it("renders model output as text, never as HTML", () => {
    const hostile = {
      ...summary,
      summary: { ...summary.summary, overview: "<script>alert(1)</script> **bold**" },
    };

    const { container } = render(
      <SummaryCard data={hostile} onRegenerate={() => {}} regenerating={false} />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script> **bold**");
  });

  it("offers to regenerate", async () => {
    const onRegenerate = vi.fn();
    render(<SummaryCard data={summary} onRegenerate={onRegenerate} regenerating={false} />);

    await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(onRegenerate).toHaveBeenCalled();
  });
});
