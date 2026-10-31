import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { readyDocument } from "../test/fixtures";
import { DocumentPanel } from "./DocumentPanel";

function renderPanel(overrides: Partial<Parameters<typeof DocumentPanel>[0]> = {}) {
  const props = {
    documents: [readyDocument],
    selectedId: null,
    onSelect: vi.fn(),
    onUploaded: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
  render(<DocumentPanel {...props} />);
  return props;
}

// userEvent.upload ignores the input's accept filter when applyAccept is off,
// which lets these tests check the component's own validation.
const user = userEvent.setup({ applyAccept: false });

describe("DocumentPanel", () => {
  it("lists documents with their status", () => {
    renderPanel({
      documents: [
        readyDocument,
        { ...readyDocument, id: 8, filename: "scan.pdf", status: "failed", error_message: "No text found." },
      ],
    });

    expect(screen.getByText("Ready - 4 pages")).toBeTruthy();
    expect(screen.getByText("No text found.")).toBeTruthy();
  });

  it("selects a document when clicked", async () => {
    const props = renderPanel();

    await user.click(screen.getByRole("button", { name: /Week 7.pdf/ }));

    expect(props.onSelect).toHaveBeenCalledWith(7);
  });

  it("uploads a PDF and reports the new document", async () => {
    const created = { ...readyDocument, id: 9, status: "processing" as const };
    const upload = vi.spyOn(api, "upload").mockResolvedValue(created);
    const props = renderPanel();
    const file = new File(["%PDF-1.7"], "lecture.pdf", { type: "application/pdf" });

    await user.upload(screen.getByLabelText("PDF file"), file);

    expect(upload).toHaveBeenCalledWith(file);
    expect(props.onUploaded).toHaveBeenCalledWith(created);
  });

  it("rejects files that aren't PDFs before uploading", async () => {
    const upload = vi.spyOn(api, "upload");
    renderPanel();

    await user.upload(screen.getByLabelText("PDF file"), new File(["hi"], "notes.txt"));

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("Only PDF files can be uploaded.");
  });

  it("shows the server's reason when an upload is rejected", async () => {
    vi.spyOn(api, "upload").mockRejectedValue(new ApiError(400, "invalid_pdf", "This file isn't a PDF."));
    renderPanel();

    await user.upload(screen.getByLabelText("PDF file"), new File(["x"], "fake.pdf"));

    expect((await screen.findByRole("alert")).textContent).toBe("This file isn't a PDF.");
  });
});
