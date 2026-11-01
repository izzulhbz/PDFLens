import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api";
import { readyDocument } from "../test/fixtures";
import { NewChat } from "./NewChat";

// userEvent.upload ignores the input's accept filter when applyAccept is off,
// which lets these tests check the component's own validation.
const user = userEvent.setup({ applyAccept: false });

function renderNewChat() {
  const props = { onUploaded: vi.fn(), onError: vi.fn() };
  render(<NewChat {...props} />);
  return props;
}

describe("NewChat", () => {
  it("uploads a chosen PDF and reports the new document", async () => {
    const created = { ...readyDocument, id: 9, status: "processing" as const };
    const upload = vi.spyOn(api, "upload").mockResolvedValue(created);
    const props = renderNewChat();
    const file = new File(["%PDF-1.7"], "lecture.pdf", { type: "application/pdf" });

    await user.upload(screen.getByLabelText("PDF file"), file);

    expect(upload).toHaveBeenCalledWith(file);
    expect(props.onUploaded).toHaveBeenCalledWith(created);
  });

  it("uploads a PDF dropped on the page", async () => {
    const upload = vi.spyOn(api, "upload").mockResolvedValue(readyDocument);
    const props = renderNewChat();
    const file = new File(["%PDF-1.7"], "dropped.pdf", { type: "application/pdf" });

    fireEvent.drop(screen.getByRole("heading", { name: "What are you studying?" }), {
      dataTransfer: { files: [file] },
    });

    expect(upload).toHaveBeenCalledWith(file);
    await vi.waitFor(() => expect(props.onUploaded).toHaveBeenCalledWith(readyDocument));
  });

  it("rejects files that aren't PDFs before uploading", async () => {
    const upload = vi.spyOn(api, "upload");
    renderNewChat();

    await user.upload(screen.getByLabelText("PDF file"), new File(["hi"], "notes.txt"));

    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toBe("Only PDF files can be uploaded.");
  });

  it("shows the server's reason when an upload is rejected", async () => {
    vi.spyOn(api, "upload").mockRejectedValue(new ApiError(400, "invalid_pdf", "This file isn't a PDF."));
    renderNewChat();

    await user.upload(screen.getByLabelText("PDF file"), new File(["x"], "fake.pdf"));

    expect((await screen.findByRole("alert")).textContent).toBe("This file isn't a PDF.");
  });
});
