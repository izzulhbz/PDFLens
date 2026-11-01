import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { readyDocument } from "../test/fixtures";
import type { PdfDocument } from "../types";
import { HistoryPanel } from "./HistoryPanel";

const titled: PdfDocument = { ...readyDocument, title: "Vector search basics" };

function renderPanel(documents: PdfDocument[] = [titled]) {
  const props = {
    user: { id: 1, email: "alice@example.com" },
    documents,
    selectedId: null,
    onSelect: vi.fn(),
    onNewChat: vi.fn(),
    onDeleted: vi.fn(),
    onOpenSettings: vi.fn(),
    onError: vi.fn(),
  };
  render(<HistoryPanel {...props} />);
  return props;
}

describe("HistoryPanel", () => {
  it("is headed History and names chats after what the PDF is about", () => {
    renderPanel([titled, { ...readyDocument, id: 8, filename: "untitled.pdf" }]);

    expect(screen.getByRole("heading", { name: "History" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Vector search basics" })).toBeTruthy();
    // No summary yet, so no title: the filename stands in.
    expect(screen.getByRole("button", { name: "untitled.pdf" })).toBeTruthy();
  });

  it("shows processing and failed chats", () => {
    renderPanel([
      { ...readyDocument, id: 8, status: "processing" },
      { ...readyDocument, id: 9, filename: "scan.pdf", status: "failed" },
    ]);

    expect(screen.getByText("Reading the PDF...")).toBeTruthy();
    expect(screen.getByText("Couldn't be processed")).toBeTruthy();
  });

  it("opens a chat, starts a new one, and opens settings", async () => {
    const props = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Vector search basics" }));
    await userEvent.click(screen.getByRole("button", { name: "New chat" }));
    await userEvent.click(screen.getByRole("button", { name: "Settings" }));

    expect(props.onSelect).toHaveBeenCalledWith(7);
    expect(props.onNewChat).toHaveBeenCalled();
    expect(props.onOpenSettings).toHaveBeenCalled();
  });

  it("deletes a chat only after confirmation", async () => {
    const remove = vi.spyOn(api, "deleteDocument").mockResolvedValue(undefined);
    const props = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Delete chat Vector search basics" }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByText('Delete "Vector search basics"?')).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(remove).toHaveBeenCalledWith(7);
    expect(props.onDeleted).toHaveBeenCalledWith(7);
  });

  it("keeps the chat when deletion is cancelled", async () => {
    const remove = vi.spyOn(api, "deleteDocument");
    const props = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Delete chat Vector search basics" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(remove).not.toHaveBeenCalled();
    expect(props.onDeleted).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Vector search basics" })).toBeTruthy();
  });

  it("reports a failed deletion and keeps the chat", async () => {
    const failure = new ApiError(409, "document_processing", "Wait until processing finishes.");
    vi.spyOn(api, "deleteDocument").mockRejectedValue(failure);
    const props = renderPanel();

    await userEvent.click(screen.getByRole("button", { name: "Delete chat Vector search basics" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(props.onError).toHaveBeenCalledWith(failure);
    expect(props.onDeleted).not.toHaveBeenCalled();
  });

  it("can't delete a chat whose PDF is still processing", () => {
    renderPanel([{ ...titled, status: "processing" }]);

    const button = screen.getByRole<HTMLButtonElement>("button", {
      name: "Delete chat Vector search basics",
    });
    expect(button.disabled).toBe(true);
  });
});
