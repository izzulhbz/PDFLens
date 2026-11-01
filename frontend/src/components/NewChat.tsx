import { useRef, useState, type DragEvent } from "react";

import { api, ApiError } from "../api";
import type { PdfDocument } from "../types";
import { FileIcon } from "./icons";

// Checked here only to give quick feedback; the server enforces the real rules.
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

interface Props {
  onUploaded: (document: PdfDocument) => void;
  onError: (error: unknown) => void;
}

/** A new chat starts with a PDF: pick one, or drop it on the page. */
export function NewChat({ onUploaded, onError }: Props) {
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function upload(file: File | undefined) {
    if (!file || uploading) return;
    setUploadError(null);
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only PDF files can be uploaded.");
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError("PDFs can be at most 20 MB.");
      return;
    }

    setUploading(true);
    try {
      onUploaded(await api.upload(file));
    } catch (err) {
      if (err instanceof ApiError && err.status !== 401) setUploadError(err.message);
      else onError(err);
    } finally {
      setUploading(false);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void upload(event.dataTransfer.files[0]);
  }

  return (
    <section className="chat new-chat-view" aria-label="New chat">
      <div
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <FileIcon size={40} />
        <h1>What are you studying?</h1>
        <p className="muted">
          Upload a lecture PDF. PDFLens summarises what it teaches, then answers your questions
          with page citations.
        </p>
        <button type="button" onClick={() => input.current?.click()} disabled={uploading}>
          {uploading ? "Uploading..." : "Upload PDF"}
        </button>
        <p className="hint">or drop it here. PDF only, up to 20 MB.</p>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          aria-label="PDF file"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = ""; // allow choosing the same file again
            void upload(file);
          }}
        />
        {uploadError && (
          <p role="alert" className="error">
            {uploadError}
          </p>
        )}
      </div>
    </section>
  );
}
