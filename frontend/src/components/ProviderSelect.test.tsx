import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { providers } from "../test/fixtures";
import { ProviderSelect } from "./ProviderSelect";

describe("ProviderSelect", () => {
  it("disables providers the backend reports as unavailable", () => {
    render(<ProviderSelect providers={providers} value="auto" onChange={() => {}} />);

    const anthropic = screen.getByRole<HTMLOptionElement>("option", { name: /Anthropic/ });
    const ollama = screen.getByRole<HTMLOptionElement>("option", { name: "Ollama (llama3.2)" });
    const gpu = screen.getByRole<HTMLOptionElement>("option", { name: "Ollama GPU (qwen2.5:7b)" });
    expect(anthropic.disabled).toBe(true);
    expect(anthropic.textContent).toContain("unavailable");
    expect(anthropic.title).toBe("No API key configured");
    expect(ollama.disabled).toBe(false);
    expect(gpu.disabled).toBe(false);
  });

  it("reports the chosen provider", async () => {
    const onChange = vi.fn();
    render(<ProviderSelect providers={providers} value="auto" onChange={onChange} />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "ollama");

    expect(onChange).toHaveBeenCalledWith("ollama");
  });
});
