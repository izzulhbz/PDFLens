import { useRef, useState, type ChangeEvent } from "react";

import { api, ApiError } from "../api";
import type { PdfDocument } from "../types";

// Checked here only to give quick feedback; the server enforces the real rules.
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

const STATUS_LABELS: Record<PdfDocument["status"], string> = {
  processing: "Processing...",
  ready: "Ready",
  failed: "Failed",
};

interface Props {
  documents: PdfDocument[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onUploaded: (document: PdfDocument) => void;
  onError: (error: unknown) => void;
}

export function DocumentPanel({ documents, selectedId, onSelect, onUploaded, onError }: Props) {
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow choosing the same file again
    if (!file) return;
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
      if (err instanceof ApiError && err.status !== 401) {
        setUploadError(err.message);
      } else {
        onError(err);
      }
    } finally {
      setUploading(false);
    }
  }

  return (
    <aside className="documents">
      <h2>Your documents</h2>
      <button type="button" onClick={() => input.current?.click()} disabled={uploading}>
        {uploading ? "Uploading..." : "Upload PDF"}
      </button>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        aria-label="PDF file"
        hidden
        onChange={handleFile}
      />
      {uploadError && (
        <p role="alert" className="error">
          {uploadError}
        </p>
      )}

      {documents.length === 0 ? (
        <p className="muted">No documents yet. Upload a lecture PDF to start.</p>
      ) : (
        <ul>
          {documents.map((doc) => (
            <li key={doc.id}>
              <button
                type="button"
                className={`document ${doc.id === selectedId ? "selected" : ""}`}
                aria-pressed={doc.id === selectedId}
                onClick={() => onSelect(doc.id)}
              >
                <span className="filename">{doc.filename}</span>
                <span className={`status status-${doc.status}`}>
                  {STATUS_LABELS[doc.status]}
                  {doc.page_count ? ` - ${doc.page_count} pages` : ""}
                </span>
                {doc.status === "failed" && doc.error_message && (
                  <span className="error small">{doc.error_message}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
