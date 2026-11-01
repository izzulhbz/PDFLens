import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { providers } from "../test/fixtures";
import type { ProvidersResponse } from "../types";
import { DefaultModelSelect, ProviderSelect, resolveDefault } from "./ProviderSelect";

// In `providers`, Anthropic is unavailable (no key) and both Ollamas are
// available. This variant has Anthropic available too.
const anthropicUp: ProvidersResponse = {
  ...providers,
  providers: providers.providers.map((p) =>
    p.name === "anthropic" ? { ...p, available: true, detail: "Reachable" } : p,
  ),
};

describe("ProviderSelect", () => {
  it("groups models under Cloud LLM and Local LLM and disables unavailable ones", () => {
    render(<ProviderSelect providers={providers} value="auto" onChange={() => {}} defaultModel="ollama_gpu" />);

    const cloud = screen.getByRole("group", { name: "Cloud LLM" });
    const local = screen.getByRole("group", { name: "Local LLM" });
    const anthropic = within(cloud).getByRole<HTMLOptionElement>("option", { name: /Anthropic/ });
    expect(anthropic.disabled).toBe(true);
    expect(anthropic.textContent).toContain("unavailable");
    expect(anthropic.title).toBe("No API key configured");
    expect(within(local).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Ollama GPU (qwen2.5:7b)",
      "Ollama (llama3.2)",
    ]);
  });

  it("names the default model in brackets after Default", () => {
    render(<ProviderSelect providers={anthropicUp} value="auto" onChange={() => {}} defaultModel="anthropic" />);

    expect(screen.getByRole("option", { name: "Default (Anthropic)" })).toBeTruthy();
  });

  it("says which model Default really uses when the default one is unavailable", () => {
    render(<ProviderSelect providers={providers} value="auto" onChange={() => {}} defaultModel="anthropic" />);

    expect(screen.getByRole("option", { name: "Default (Ollama GPU, Anthropic unavailable)" })).toBeTruthy();
  });

  it("reports the chosen model", async () => {
    const onChange = vi.fn();
    render(<ProviderSelect providers={providers} value="auto" onChange={onChange} defaultModel="anthropic" />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "ollama");

    expect(onChange).toHaveBeenCalledWith("ollama");
  });
});

describe("resolveDefault", () => {
  it("uses the default model, else the next available in the backend's order", () => {
    expect(resolveDefault(anthropicUp, "ollama")).toBe("ollama");
    expect(resolveDefault(providers, "anthropic")).toBe("ollama_gpu");
    expect(resolveDefault(null, "anthropic")).toBeNull();
  });
});

describe("DefaultModelSelect", () => {
  it("lets an unavailable model be chosen as the default", async () => {
    const onChange = vi.fn();
    render(<DefaultModelSelect providers={providers} value="ollama" onChange={onChange} />);

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Default model" }), "anthropic");

    expect(onChange).toHaveBeenCalledWith("anthropic");
  });
});
