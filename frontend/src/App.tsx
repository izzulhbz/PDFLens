import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";
import { ChatView, type ChatEntry } from "./components/ChatView";
import { DocumentPanel } from "./components/DocumentPanel";
import { LoginPage } from "./components/LoginPage";
import type { PdfDocument, ProvidersResponse, User } from "./types";
import { useStoredProvider } from "./useStoredProvider";

// How often to re-check documents that are still processing.
const POLL_INTERVAL_MS = 2000;

export function App() {
  // undefined = still checking the session, null = logged out.
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api.me().then(setUser, () => setUser(null));
  }, []);

  if (user === undefined) return <p className="muted center">Loading...</p>;
  if (user === null) return <LoginPage onLoggedIn={setUser} />;
  return <Workspace user={user} onLoggedOut={() => setUser(null)} />;
}

function Workspace({ user, onLoggedOut }: { user: User; onLoggedOut: () => void }) {
  const [documents, setDocuments] = useState<PdfDocument[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [histories, setHistories] = useState<Record<number, ChatEntry[]>>({});
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [provider, setProvider] = useStoredProvider();
  const [error, setError] = useState<string | null>(null);

  // A 401 anywhere means the session expired: go back to the login page.
  const handleError = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) onLoggedOut();
      else setError(err instanceof ApiError ? err.message : "Something went wrong.");
    },
    [onLoggedOut],
  );

  const refreshDocuments = useCallback(() => {
    api.listDocuments().then(setDocuments, handleError);
  }, [handleError]);

  useEffect(() => {
    refreshDocuments();
    api.providers().then(setProviders, handleError);
  }, [refreshDocuments, handleError]);

  // Poll only while something is processing, and stop as soon as nothing is.
  const anyProcessing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!anyProcessing) return;
    const timer = window.setInterval(refreshDocuments, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [anyProcessing, refreshDocuments]);

  // If the remembered provider isn't available, fall back to Auto.
  const chosen = providers?.providers.find((p) => p.name === provider);
  const effectiveProvider = chosen && !chosen.available ? "auto" : provider;

  const selected = documents.find((d) => d.id === selectedId) ?? null;

  async function logout() {
    await api.logout().catch(() => undefined);
    onLoggedOut();
  }

  return (
    <div className="workspace">
      <header className="topbar">
        <strong>PDFLens</strong>
        <span className="muted">{user.email}</span>
        <button type="button" className="link" onClick={logout}>
          Log out
        </button>
      </header>
      {error && (
        <p role="alert" className="error banner">
          {error}{" "}
          <button type="button" className="link" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <div className="layout">
        <DocumentPanel
          documents={documents}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onUploaded={(doc) => {
            setDocuments((current) => [doc, ...current.filter((d) => d.id !== doc.id)]);
            setSelectedId(doc.id);
          }}
          onError={handleError}
        />
        {selected ? (
          <ChatView
            key={selected.id}
            document={selected}
            history={histories[selected.id] ?? []}
            onHistoryChange={(entries) =>
              setHistories((current) => ({ ...current, [selected.id]: entries }))
            }
            providers={providers}
            provider={effectiveProvider}
            onProviderChange={setProvider}
            onError={handleError}
          />
        ) : (
          <section className="chat empty">
            <p className="muted">Select or upload a document to ask questions about it.</p>
          </section>
        )}
      </div>
    </div>
  );
}
