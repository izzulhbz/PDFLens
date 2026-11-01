import { useEffect, useRef } from "react";

import { THEMES, TEXT_SIZES, type Settings } from "../settings";
import { SUMMARY_LENGTHS, TONES, type ProvidersResponse } from "../types";
import { CloseIcon } from "./icons";
import { ProviderSelect } from "./ProviderSelect";

const TONE_LABELS: Record<Settings["tone"], [string, string]> = {
  professional: ["Professional", "Clear and businesslike"],
  simple: ["Simple", "Plain words, jargon explained"],
  friendly: ["Friendly", "Warm and encouraging"],
  academic: ["Academic", "Formal, precise terminology"],
};
const LENGTH_LABELS: Record<Settings["length"], string> = {
  brief: "Brief",
  standard: "Standard",
  detailed: "Detailed",
};
const THEME_LABELS: Record<Settings["theme"], string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};
const TEXT_SIZE_LABELS: Record<Settings["textSize"], string> = {
  small: "Small",
  default: "Default",
  large: "Large",
};

interface ChoiceProps<T extends string> {
  legend: string;
  name: string;
  options: readonly T[];
  value: T;
  label: (option: T) => string;
  hint?: (option: T) => string;
  onChange: (option: T) => void;
}

/** A row of mutually exclusive options: real radio buttons, styled as pills. */
function Choice<T extends string>({ legend, name, options, value, label, hint, onChange }: ChoiceProps<T>) {
  return (
    <fieldset className="choice">
      <legend>{legend}</legend>
      <div className="choice-options">
        {options.map((option) => (
          <label key={option} className={option === value ? "chosen" : ""} title={hint?.(option)}>
            <input
              type="radio"
              name={name}
              value={option}
              checked={option === value}
              onChange={() => onChange(option)}
            />
            {label(option)}
          </label>
        ))}
      </div>
      {hint && <p className="hint">{hint(value)}</p>}
    </fieldset>
  );
}

interface Props {
  settings: Settings;
  onChange: (changes: Partial<Settings>) => void;
  providers: ProvidersResponse | null;
  onClose: () => void;
  onLogout: () => void;
}

export function SettingsPanel({ settings, onChange, providers, onClose, onLogout }: Props) {
  const dialog = useRef<HTMLDivElement>(null);

  // Escape closes the panel; focus moves into it so keyboard users land there.
  useEffect(() => {
    dialog.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={dialog}
        className="settings"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        tabIndex={-1}
      >
        <header className="settings-header">
          <h2 id="settings-title">Settings</h2>
          <button type="button" className="icon-button" aria-label="Close settings" onClick={onClose}>
            <CloseIcon />
          </button>
        </header>

        <section>
          <h3>Summaries</h3>
          <Choice
            legend="Tone"
            name="tone"
            options={TONES}
            value={settings.tone}
            label={(t) => TONE_LABELS[t][0]}
            hint={(t) => TONE_LABELS[t][1]}
            onChange={(tone) => onChange({ tone })}
          />
          <Choice
            legend="Length"
            name="length"
            options={SUMMARY_LENGTHS}
            value={settings.length}
            label={(l) => LENGTH_LABELS[l]}
            onChange={(length) => onChange({ length })}
          />
          <label className="toggle">
            <input
              type="checkbox"
              checked={settings.includeCharts}
              onChange={(e) => onChange({ includeCharts: e.target.checked })}
            />
            <span>
              Include charts
              <span className="hint">
                Draws charts when the PDF contains numeric data, such as a table of results.
                Only numbers found in the PDF are plotted.
              </span>
            </span>
          </label>
          <p className="hint">
            New summaries use these settings. Open a chat and choose Regenerate to update an
            existing summary.
          </p>
        </section>

        <section>
          <h3>Answers</h3>
          <ProviderSelect
            providers={providers}
            value={settings.provider}
            onChange={(provider) => onChange({ provider })}
          />
        </section>

        <section>
          <h3>Appearance</h3>
          <Choice
            legend="Theme"
            name="theme"
            options={THEMES}
            value={settings.theme}
            label={(t) => THEME_LABELS[t]}
            onChange={(theme) => onChange({ theme })}
          />
          <Choice
            legend="Text size"
            name="text-size"
            options={TEXT_SIZES}
            value={settings.textSize}
            label={(s) => TEXT_SIZE_LABELS[s]}
            onChange={(textSize) => onChange({ textSize })}
          />
        </section>

        <footer className="settings-footer">
          <button type="button" className="ghost" onClick={onLogout}>
            Log out
          </button>
        </footer>
      </div>
    </div>
  );
}
