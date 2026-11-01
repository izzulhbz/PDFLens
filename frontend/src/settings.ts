// The user's settings, remembered in this browser (localStorage).
//
// Nothing here is secret or security-relevant: the backend checks every
// summary setting against its own allowlist, so a value edited by hand in
// localStorage can at worst be ignored here or rejected there.

import { useCallback, useEffect, useState } from "react";

import {
  MODEL_NAMES,
  PROVIDER_NAMES,
  SUMMARY_LENGTHS,
  TONES,
  type ModelName,
  type ProviderName,
  type SummaryLength,
  type SummaryOptions,
  type Tone,
} from "./types";

export const THEMES = ["light", "dark", "system"] as const;
export type Theme = (typeof THEMES)[number];
export const TEXT_SIZES = ["small", "default", "large"] as const;
export type TextSize = (typeof TEXT_SIZES)[number];

export interface Settings {
  tone: Tone;
  length: SummaryLength;
  includeCharts: boolean;
  /** The model a chat set to "Default" uses (falling back to the others if it fails). */
  defaultModel: ModelName;
  /** The model picker in the chat: "auto" means Default. */
  provider: ProviderName;
  theme: Theme;
  textSize: TextSize;
}

export const DEFAULT_SETTINGS: Settings = {
  tone: "professional",
  length: "standard",
  includeCharts: true,
  defaultModel: "anthropic",
  provider: "auto",
  theme: "light",
  textSize: "default",
};

export const SETTINGS_STORAGE_KEY = "pdflens.settings";

function pick<T extends string>(allowed: readonly T[], value: unknown, fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

/** Stored settings, with anything unknown or missing replaced by its default. */
export function readSettings(): Settings {
  let stored: Record<string, unknown> = {};
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : {};
    if (parsed && typeof parsed === "object") stored = parsed as Record<string, unknown>;
  } catch {
    // Blocked storage (private mode, strict settings) or broken JSON: use the defaults.
  }
  const d = DEFAULT_SETTINGS;
  return {
    tone: pick(TONES, stored.tone, d.tone),
    length: pick(SUMMARY_LENGTHS, stored.length, d.length),
    includeCharts:
      typeof stored.includeCharts === "boolean" ? stored.includeCharts : d.includeCharts,
    defaultModel: pick(MODEL_NAMES, stored.defaultModel, d.defaultModel),
    provider: pick(PROVIDER_NAMES, stored.provider, d.provider),
    theme: pick(THEMES, stored.theme, d.theme),
    textSize: pick(TEXT_SIZES, stored.textSize, d.textSize),
  };
}

/** The settings, and a function that changes some of them and remembers the result. */
export function useSettings(): [Settings, (changes: Partial<Settings>) => void] {
  const [settings, setSettings] = useState<Settings>(readSettings);

  const update = useCallback((changes: Partial<Settings>) => {
    setSettings((current) => {
      const next = { ...current, ...changes };
      try {
        window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Not remembered, but the change still applies for this visit.
      }
      return next;
    });
  }, []);

  return [settings, update];
}

/** The summary settings in the shape the backend expects. */
export function summaryOptions(settings: Settings): SummaryOptions {
  return { tone: settings.tone, length: settings.length, include_charts: settings.includeCharts };
}

export function sameSummaryOptions(a: SummaryOptions | null, b: SummaryOptions): boolean {
  return (
    a !== null && a.tone === b.tone && a.length === b.length && a.include_charts === b.include_charts
  );
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

/**
 * Applies the theme and text size to <html> (as data attributes the CSS
 * reads). "system" follows the operating system, including when it changes.
 */
export function useAppearance(theme: Theme, textSize: TextSize) {
  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      root.dataset.theme = theme === "system" ? (systemPrefersDark() ? "dark" : "light") : theme;
    };
    apply();
    if (theme !== "system" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.textSize = textSize;
  }, [textSize]);
}
