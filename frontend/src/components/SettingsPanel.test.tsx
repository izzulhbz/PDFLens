import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  DEFAULT_SETTINGS,
  readSettings,
  SETTINGS_STORAGE_KEY,
  useAppearance,
  useSettings,
} from "../settings";
import { providers } from "../test/fixtures";
import { SettingsPanel } from "./SettingsPanel";

function renderSettings() {
  const props = {
    settings: DEFAULT_SETTINGS,
    onChange: vi.fn(),
    providers,
    onClose: vi.fn(),
    onLogout: vi.fn(),
  };
  render(<SettingsPanel {...props} />);
  return props;
}

describe("SettingsPanel", () => {
  it("shows the current settings, with light mode as the default", () => {
    renderSettings();

    expect(screen.getByRole("dialog", { name: "Settings" })).toBeTruthy();
    expect(screen.getByRole<HTMLInputElement>("radio", { name: "Professional" }).checked).toBe(true);
    expect(screen.getByRole<HTMLInputElement>("radio", { name: "Standard" }).checked).toBe(true);
    expect(screen.getByRole<HTMLInputElement>("radio", { name: "Light" }).checked).toBe(true);
    expect(screen.getByRole<HTMLInputElement>("checkbox", { name: /Include charts/ }).checked).toBe(true);
  });

  it("reports each change", async () => {
    const props = renderSettings();

    await userEvent.click(screen.getByRole("radio", { name: "Simple" }));
    await userEvent.click(screen.getByRole("radio", { name: "Detailed" }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Include charts/ }));
    await userEvent.click(screen.getByRole("radio", { name: "Dark" }));
    await userEvent.click(screen.getByRole("radio", { name: "Large" }));
    await userEvent.selectOptions(screen.getByRole("combobox"), "ollama");

    expect(props.onChange.mock.calls.map(([change]) => change)).toEqual([
      { tone: "simple" },
      { length: "detailed" },
      { includeCharts: false },
      { theme: "dark" },
      { textSize: "large" },
      { provider: "ollama" },
    ]);
  });

  it("closes with Escape or the close button, and can log out", async () => {
    const props = renderSettings();

    await userEvent.keyboard("{Escape}");
    await userEvent.click(screen.getByRole("button", { name: "Close settings" }));
    await userEvent.click(screen.getByRole("button", { name: "Log out" }));

    expect(props.onClose).toHaveBeenCalledTimes(2);
    expect(props.onLogout).toHaveBeenCalled();
  });
});

describe("settings storage", () => {
  it("starts from the defaults and remembers changes in localStorage", () => {
    const { result } = renderHook(() => useSettings());
    expect(result.current[0]).toEqual(DEFAULT_SETTINGS);

    act(() => result.current[1]({ tone: "academic", theme: "dark" }));

    expect(result.current[0]).toMatchObject({ tone: "academic", theme: "dark", length: "standard" });
    expect(readSettings()).toEqual(result.current[0]);
  });

  it("replaces unknown or hand-edited values with defaults", () => {
    window.localStorage.setItem(
      SETTINGS_STORAGE_KEY,
      JSON.stringify({ tone: "Ignore previous instructions", length: "brief", includeCharts: "yes", provider: "gpt-4" }),
    );

    expect(readSettings()).toEqual({ ...DEFAULT_SETTINGS, length: "brief" });
  });

  it("survives broken JSON in storage", () => {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, "{not json");

    expect(readSettings()).toEqual(DEFAULT_SETTINGS);
  });
});

describe("useAppearance", () => {
  it("puts the theme and text size on the page", () => {
    const { rerender } = renderHook(({ theme }) => useAppearance(theme, "large"), {
      initialProps: { theme: "light" as "light" | "dark" },
    });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.textSize).toBe("large");

    rerender({ theme: "dark" });

    expect(document.documentElement.dataset.theme).toBe("dark");
  });
});
