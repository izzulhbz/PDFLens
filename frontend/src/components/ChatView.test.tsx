import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { answer, defaultOptions, providers, readyDocument, summary } from "../test/fixtures";
import type { ModelName, PdfDocument, ProviderName, SummaryResponse } from "../types";
import { ChatView, type ChatEntry } from "./ChatView";

const onSummary = vi.fn();
const onProviderChange = vi.fn();

// ChatView keeps no history itself; this wrapper plays the parent's part.
function Harness({
  document = readyDocument,
  provider = "ollama" as ProviderName,
  prefer = "anthropic" as ModelName,
  // null: a chat reopened from History, whose messages aren't loaded yet.
  initialHistory = [] as ChatEntry[] | null,
}) {
  const [history, setHistory] = useState<ChatEntry[] | undefined>(initialHistory ?? undefined);
  return (
    <ChatView
      document={document}
      history={history}
      onHistoryChange={setHistory}
      model={{ provider, prefer }}
      providers={providers}
      onProviderChange={onProviderChange}
      summaryOptions={defaultOptions}
      onSummary={onSummary}
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
    expect(create).toHaveBeenCalledWith(7, { provider: "ollama", prefer: "anthropic" }, defaultOptions);
    // The summary's title becomes the chat's name in History.
    expect(onSummary).toHaveBeenCalledWith(7, "Retrieval-Augmented Generation");
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

    expect(ask).toHaveBeenCalledWith(7, "What does HNSW build?", {
      provider: "ollama",
      prefer: "anthropic",
    });
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

    expect(screen.getByLabelText<HTMLTextAreaElement>("Your question").disabled).toBe(true);
    expect(screen.getByText(/Reading your PDF/)).toBeTruthy();
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

describe("ChatView: reopening a chat", () => {
  it("loads the earlier questions and answers from the server", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(summary);
    const messages = vi
      .spyOn(api, "messages")
      .mockResolvedValue([{ ...answer, question: "What does HNSW build?", asked_at: "2026-11-01T10:10:00Z" }]);

    render(<Harness initialHistory={null} />);

    expect(await screen.findByText("What does HNSW build?")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show source for [p. 3]" })).toBeTruthy();
    expect(messages).toHaveBeenCalledWith(7);
  });

  it("doesn't reload a chat it already has", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(summary);
    const messages = vi.spyOn(api, "messages");

    render(<Harness initialHistory={[{ question: "Earlier question", answer }]} />);

    expect(await screen.findByText("Earlier question")).toBeTruthy();
    expect(messages).not.toHaveBeenCalled();
  });
});

describe("ChatView: model picker", () => {
  it("shows Default with the default model in brackets, and reports changes", async () => {
    vi.spyOn(api, "getSummary").mockResolvedValue(summary);
    render(<Harness provider="auto" prefer="ollama_gpu" />);
    await screen.findByText(/How RAG answers questions/);

    const picker = screen.getByRole<HTMLSelectElement>("combobox", { name: "Model" });
    expect(picker.value).toBe("auto");
    expect(screen.getByRole("option", { name: "Default (Ollama GPU)" })).toBeTruthy();

    await userEvent.selectOptions(picker, "ollama");

    expect(onProviderChange).toHaveBeenCalledWith("ollama");
  });
});
