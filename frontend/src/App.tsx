import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";
import { ChatView, type ChatEntry } from "./components/ChatView";
import { HistoryPanel } from "./components/HistoryPanel";
import { MenuIcon } from "./components/icons";
import { LoginPage } from "./components/LoginPage";
import { NewChat } from "./components/NewChat";
import { SettingsPanel } from "./components/SettingsPanel";
import { summaryOptions, useAppearance, useSettings, type Settings } from "./settings";
import type { PdfDocument, ProvidersResponse, User } from "./types";

// How often to re-check documents that are still processing.
const POLL_INTERVAL_MS = 2000;

export function App() {
  // undefined = still checking the session, null = logged out.
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [settings, updateSettings] = useSettings();
  useAppearance(settings.theme, settings.textSize);

  useEffect(() => {
    api.me().then(setUser, () => setUser(null));
  }, []);

  if (user === undefined) return <p className="muted center">Loading...</p>;
  if (user === null) return <LoginPage onLoggedIn={setUser} />;
  return (
    <Workspace
      user={user}
      settings={settings}
      onSettingsChange={updateSettings}
      onLoggedOut={() => setUser(null)}
    />
  );
}

interface WorkspaceProps {
  user: User;
  settings: Settings;
  onSettingsChange: (changes: Partial<Settings>) => void;
  onLoggedOut: () => void;
}

function Workspace({ user, settings, onSettingsChange, onLoggedOut }: WorkspaceProps) {
  const [documents, setDocuments] = useState<PdfDocument[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // Each chat's messages, loaded from the server the first time it's opened.
  const [histories, setHistories] = useState<Record<number, ChatEntry[]>>({});
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Small screens only: the History panel slides over the chat.
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

  // If the remembered model isn't available, use Default instead.
  const chosen = providers?.providers.find((p) => p.name === settings.provider);
  const effectiveProvider = chosen && !chosen.available ? "auto" : settings.provider;

  const selected = documents.find((d) => d.id === selectedId) ?? null;

  function open(id: number | null) {
    setSelectedId(id);
    setSidebarOpen(false);
  }

  // The summary names the chat: show its title in History straight away.
  const nameChat = useCallback((documentId: number, title: string) => {
    setDocuments((current) =>
      current.map((d) => (d.id === documentId && d.title !== title ? { ...d, title } : d)),
    );
  }, []);

  function forget(documentId: number) {
    setDocuments((current) => current.filter((d) => d.id !== documentId));
    setHistories((current) => {
      const next = { ...current };
      delete next[documentId];
      return next;
    });
    if (selectedId === documentId) setSelectedId(null);
  }

  async function logout() {
    await api.logout().catch(() => undefined);
    onLoggedOut();
  }

  return (
    <div className={`app ${sidebarOpen ? "sidebar-open" : ""}`}>
      <HistoryPanel
        user={user}
        documents={documents}
        selectedId={selectedId}
        onSelect={open}
        onNewChat={() => open(null)}
        onDeleted={forget}
        onOpenSettings={() => setSettingsOpen(true)}
        onError={handleError}
      />
      <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} aria-hidden="true" />

      <main className="main">
        <div className="mobile-bar">
          <button
            type="button"
            className="icon-button"
            aria-label="Show history"
            onClick={() => setSidebarOpen(true)}
          >
            <MenuIcon />
          </button>
          <strong>PDFLens</strong>
        </div>
        {error && (
          <p role="alert" className="error banner">
            {error}{" "}
            <button type="button" className="link" onClick={() => setError(null)}>
              Dismiss
            </button>
          </p>
        )}
        {selected ? (
          <ChatView
            key={selected.id}
            document={selected}
            history={histories[selected.id]}
            onHistoryChange={(entries) =>
              setHistories((current) => ({ ...current, [selected.id]: entries }))
            }
            model={{ provider: effectiveProvider, prefer: settings.defaultModel }}
            providers={providers}
            onProviderChange={(provider) => onSettingsChange({ provider })}
            summaryOptions={summaryOptions(settings)}
            onSummary={nameChat}
            onError={handleError}
          />
        ) : (
          <NewChat
            onUploaded={(doc) => {
              setDocuments((current) => [doc, ...current.filter((d) => d.id !== doc.id)]);
              setHistories((current) => ({ ...current, [doc.id]: [] }));
              open(doc.id);
            }}
            onError={handleError}
          />
        )}
      </main>

      {settingsOpen && (
        <SettingsPanel
          settings={settings}
          onChange={onSettingsChange}
          providers={providers}
          onClose={() => setSettingsOpen(false)}
          onLogout={logout}
        />
      )}
    </div>
  );
}
