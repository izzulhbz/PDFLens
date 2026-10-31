import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { providers } from "../test/fixtures";
import { PROVIDER_STORAGE_KEY, useStoredProvider } from "../useStoredProvider";
import { ProviderSelect } from "./ProviderSelect";

describe("ProviderSelect", () => {
  it("disables providers the backend reports as unavailable", () => {
    render(<ProviderSelect providers={providers} value="auto" onChange={() => {}} />);

    const anthropic = screen.getByRole<HTMLOptionElement>("option", { name: /Anthropic/ });
    const ollama = screen.getByRole<HTMLOptionElement>("option", { name: /Ollama/ });
    expect(anthropic.disabled).toBe(true);
    expect(anthropic.textContent).toContain("unavailable");
    expect(anthropic.title).toBe("No API key configured");
    expect(ollama.disabled).toBe(false);
  });

  it("reports the chosen provider", async () => {
    const onChange = vi.fn();
    render(<ProviderSelect providers={providers} value="auto" onChange={onChange} />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "ollama");

    expect(onChange).toHaveBeenCalledWith("ollama");
  });
});

describe("useStoredProvider", () => {
  it("defaults to auto and remembers the choice in localStorage", () => {
    const { result } = renderHook(() => useStoredProvider());
    expect(result.current[0]).toBe("auto");

    act(() => result.current[1]("ollama"));

    expect(result.current[0]).toBe("ollama");
    expect(window.localStorage.getItem(PROVIDER_STORAGE_KEY)).toBe("ollama");
  });

  it("restores a stored choice", () => {
    window.localStorage.setItem(PROVIDER_STORAGE_KEY, "anthropic");

    expect(renderHook(() => useStoredProvider()).result.current[0]).toBe("anthropic");
  });

  it("ignores a stored value that isn't a known provider", () => {
    window.localStorage.setItem(PROVIDER_STORAGE_KEY, "gpt-4");

    expect(renderHook(() => useStoredProvider()).result.current[0]).toBe("auto");
  });
});
