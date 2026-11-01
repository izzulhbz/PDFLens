import { useState } from "react";

import { api, ApiError } from "../api";
import type { PdfDocument, User } from "../types";
import { GearIcon, PlusIcon, TrashIcon } from "./icons";

const STATUS_LABELS: Record<PdfDocument["status"], string> = {
  processing: "Reading the PDF...",
  ready: "",
  failed: "Couldn't be processed",
};

/** A chat is named after what its PDF is about, or the filename until the summary exists. */
export function chatTitle(document: PdfDocument): string {
  return document.title || document.filename;
}

interface Props {
  user: User;
  documents: PdfDocument[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onNewChat: () => void;
  onDeleted: (id: number) => void;
  onOpenSettings: () => void;
  onError: (error: unknown) => void;
}

/** The sidebar: a new chat button, every chat so far, and settings at the bottom. */
export function HistoryPanel(props: Props) {
  const { documents, selectedId, onSelect, onDeleted, onError } = props;
  // The chat whose delete button was clicked, waiting for confirmation.
  const [confirming, setConfirming] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  async function remove(id: number) {
    setDeleting(id);
    try {
      await api.deleteDocument(id);
      onDeleted(id);
    } catch (err) {
      // Already gone (deleted in another tab, say): drop it from the list too.
      if (err instanceof ApiError && err.status === 404) onDeleted(id);
      else onError(err);
    } finally {
      setDeleting(null);
      setConfirming(null);
    }
  }

  return (
    <nav className="sidebar" aria-label="Chats">
      <div className="sidebar-top">
        <span className="brand">PDFLens</span>
        <button type="button" className="new-chat" onClick={props.onNewChat}>
          <PlusIcon /> New chat
        </button>
      </div>

      <h2 className="history-heading">History</h2>
      {documents.length === 0 ? (
        <p className="muted history-empty">No chats yet. Upload a PDF to start one.</p>
      ) : (
        <ul className="history">
          {documents.map((doc) => {
            const title = chatTitle(doc);
            const selected = doc.id === selectedId;
            if (confirming === doc.id) {
              return (
                <li key={doc.id} className="history-item confirming">
                  <span className="confirm-text">Delete "{title}"?</span>
                  <span className="confirm-actions">
                    <button
                      type="button"
                      className="danger small-button"
                      onClick={() => remove(doc.id)}
                      disabled={deleting === doc.id}
                    >
                      {deleting === doc.id ? "Deleting..." : "Delete"}
                    </button>
                    <button
                      type="button"
                      className="ghost small-button"
                      onClick={() => setConfirming(null)}
                    >
                      Cancel
                    </button>
                  </span>
                </li>
              );
            }
            return (
              <li key={doc.id} className={`history-item ${selected ? "selected" : ""}`}>
                <button
                  type="button"
                  className="history-open"
                  aria-current={selected ? "page" : undefined}
                  onClick={() => onSelect(doc.id)}
                  title={doc.title ? `${doc.title} (${doc.filename})` : doc.filename}
                >
                  <span className="history-title">{title}</span>
                  {doc.status !== "ready" && (
                    <span className={`history-status status-${doc.status}`}>
                      {STATUS_LABELS[doc.status]}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  className="icon-button history-delete"
                  aria-label={`Delete chat ${title}`}
                  title={
                    doc.status === "processing" ? "Wait until processing finishes" : "Delete chat"
                  }
                  disabled={doc.status === "processing"}
                  onClick={() => setConfirming(doc.id)}
                >
                  <TrashIcon size={16} />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="sidebar-bottom">
        <button type="button" className="settings-button" onClick={props.onOpenSettings}>
          <GearIcon /> Settings
        </button>
        <span className="muted small account" title={props.user.email}>
          {props.user.email}
        </span>
      </div>
    </nav>
  );
}
