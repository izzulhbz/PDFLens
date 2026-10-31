import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { answer } from "../test/fixtures";
import { AnswerMessage, splitCitations } from "./AnswerMessage";

describe("splitCitations", () => {
  it("separates text from [p. N] and [pp. N-M] citations", () => {
    expect(splitCitations("A [p. 3] and B [pp. 3-4].")).toEqual([
      { text: "A " },
      { text: "[p. 3]", first: 3, last: 3 },
      { text: " and B " },
      { text: "[pp. 3-4]", first: 3, last: 4 },
      { text: "." },
    ]);
  });
});

describe("AnswerMessage", () => {
  it("shows the provider and latency under the answer", () => {
    render(<AnswerMessage answer={answer} />);

    expect(screen.getByText(/by Ollama/).textContent).toContain("2.2 s");
  });

  it("expands the matching source when a citation is clicked", async () => {
    render(<AnswerMessage answer={answer} />);
    const source = screen.getByRole("button", { name: /Page 3 - cited/ });
    expect(source.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("HNSW builds a layered graph...")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Show source for [p. 3]" }));

    expect(source.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("HNSW builds a layered graph...")).toBeTruthy();
  });

  it("lets every source snippet be expanded and collapsed", async () => {
    render(<AnswerMessage answer={answer} />);
    const intro = screen.getByRole("button", { name: "Page 1" });

    await userEvent.click(intro);
    expect(screen.getByText("Course introduction...")).toBeTruthy();
    await userEvent.click(intro);
    expect(screen.queryByText("Course introduction...")).toBeNull();
  });

  it("renders HTML in an answer as plain text, never as markup", () => {
    const hostile = { ...answer, answer: '<img src=x onerror="alert(1)"> Look [p. 3]' };

    const { container } = render(<AnswerMessage answer={hostile} />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });

  it("labels refusals", () => {
    const refusal = { ...answer, answer: "I couldn't find this in the document.", refused: true };

    render(<AnswerMessage answer={refusal} />);

    expect(screen.getByText(/Not found in the document/)).toBeTruthy();
  });
});
