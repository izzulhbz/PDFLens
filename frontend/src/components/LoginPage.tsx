import { useState, type FormEvent } from "react";

import { api, ApiError } from "../api";
import type { User } from "../types";

const MIN_PASSWORD_LENGTH = 12; // matches the backend's rule

interface Props {
  onLoggedIn: (user: User) => void;
}

export function LoginPage({ onLoggedIn }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user =
        mode === "login" ? await api.login(email, password) : await api.register(email, password);
      onLoggedIn(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const registering = mode === "register";
  return (
    <main className="login">
      <h1>PDFLens</h1>
      <p className="muted">Ask questions about your lecture PDFs, with page citations.</p>
      <form onSubmit={submit} className="card">
        <h2>{registering ? "Create an account" : "Log in"}</h2>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete={registering ? "new-password" : "current-password"}
            required
            minLength={registering ? MIN_PASSWORD_LENGTH : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {registering && (
          <p className="hint">At least {MIN_PASSWORD_LENGTH} characters. A short phrase works well.</p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? "Please wait..." : registering ? "Create account" : "Log in"}
        </button>
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(registering ? "login" : "register");
            setError(null);
          }}
        >
          {registering ? "Already have an account? Log in" : "New here? Create an account"}
        </button>
      </form>
    </main>
  );
}
