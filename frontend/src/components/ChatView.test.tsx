import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { answer, providers, readyDocument, summary } from "../test/fixtures";
import type { PdfDocument, ProviderName, SummaryResponse } from "../types";
import { ChatView, type ChatEntry } from "./ChatView";

// ChatView keeps no history itself; this wrapper plays the parent's part.
function Harness({ document = readyDocument, provider = "ollama" as ProviderName }) {
  const [history, setHistory] = useState<ChatEntry[]>([]);
  return (
    <ChatView
      document={document}
      history={history}
      onHistoryChange={setHistory}
      providers={providers}
      provider={provider}
      onProviderChange={() => {}}
      onError={() => {}}
    />
  );
}

async function askQuestion(text: string) {
  await userEvent.type(screen.getByLabelText("Your question"), text);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
}

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("ChatView: summary first", () => {
  it("shows the saved summary, then opens the question box", async () => {
    const saved = deferred<SummaryResponse | null>();
    vi.spyOn(api, "getSummary").mockReturnValue(saved.promise);
    const create = vi.spyOn(api, "createSummary");
    render(<Harness />);

    expect(screen.getByRole("status").textContent).toContain("Summarising");
    expect(screen.getByLabelText<HTMLTextAreaElement>("Your question").disabled).toBe(true);

    saved.resolve(summary);

    expect(await screen.findByRole("heading", { name: "Retrieval-Augmented Generation" })).toBeTruthy();
    expect(screen.getByLabelText<HTMLTextAreaElement>("Your question").disabled).toBe(false);
    expect(create).not.toHaveBeenCalled();
  });

  it("writes a summary with the chosen provider when none is saved yet", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(null);
    const create = vi.spyOn(api, "createSummary").mockResolvedValue(summary);
    render(<Harness provider="ollama" />);

    expect(await screen.findByText(/How RAG answers questions/)).toBeTruthy();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith(7, "ollama");
  });

  it("shows why a summary failed, offers a retry, and still allows questions", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(null);
    const create = vi
      .spyOn(api, "createSummary")
      .mockRejectedValueOnce(new ApiError(503, "llm_unavailable", "Provider is down."))
      .mockResolvedValueOnce(summary);
    render(<Harness />);

    expect((await screen.findByRole("alert")).textContent).toContain("Provider is down.");
    expect(screen.getByLabelText<HTMLTextAreaElement>("Your question").disabled).toBe(false);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(/How RAG answers questions/)).toBeTruthy();
    expect(create).toHaveBeenCalledTimes(2);
  });
});

describe("ChatView: asking", () => {
  beforeEach(() => {
    vi.spyOn(api, "getSummary").mockResolvedValue(summary);
  });

  it("shows a loading state, then the answer with its sources", async () => {
    const pending = deferred<typeof answer>();
    const ask = vi.spyOn(api, "ask").mockReturnValue(pending.promise);
    render(<Harness />);
    await screen.findByText(/How RAG answers questions/);

    await askQuestion("What does HNSW build?");

    expect(ask).toHaveBeenCalledWith(7, "What does HNSW build?", "ollama");
    expect(screen.getByText("Thinking...")).toBeTruthy();
    expect(screen.getByRole<HTMLButtonElement>("button", { name: "Asking..." }).disabled).toBe(true);

    pending.resolve(answer);

    expect(await screen.findByRole("button", { name: "Show source for [p. 3]" })).toBeTruthy();
    expect(screen.queryByText("Thinking...")).toBeNull();
  });

  it("shows the error when the provider can't answer", async () => {
    vi.spyOn(api, "ask").mockRejectedValue(
      new ApiError(503, "llm_unavailable", "The AI provider couldn't answer right now."),
    );
    render(<Harness />);
    await screen.findByText(/How RAG answers questions/);

    await askQuestion("What is HNSW?");

    expect((await screen.findByRole("alert")).textContent).toContain("couldn't answer right now");
  });

  it("doesn't summarise or offer questions until the document is ready", () => {
    const getSummary = vi.spyOn(api, "getSummary");
    const processing: PdfDocument = { ...readyDocument, status: "processing" };

    render(<Harness document={processing} />);

    expect(screen.queryByLabelText("Your question")).toBeNull();
    expect(screen.getByText(/still being processed/)).toBeTruthy();
    expect(getSummary).not.toHaveBeenCalled();
  });

  it("explains why a failed document can't be used", () => {
    const failed: PdfDocument = {
      ...readyDocument,
      status: "failed",
      error_message: "No text could be found in this PDF.",
    };

    render(<Harness document={failed} />);

    expect(screen.getByText(/No text could be found/)).toBeTruthy();
  });
});
