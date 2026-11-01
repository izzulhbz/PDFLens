import { PROVIDER_NAMES, type ProviderName, type ProvidersResponse } from "../types";

export const PROVIDER_LABELS: Record<string, string> = {
  auto: "Auto",
  anthropic: "Anthropic",
  ollama_gpu: "Ollama GPU",
  ollama: "Ollama",
  mock: "Mock",
};

interface Props {
  providers: ProvidersResponse | null;
  value: ProviderName;
  onChange: (provider: ProviderName) => void;
}

/** Provider dropdown. Providers the backend reports as unavailable are disabled. */
export function ProviderSelect({ providers, value, onChange }: Props) {
  const options = providers?.providers ?? [];
  return (
    <label className="provider">
      Answer with
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as ProviderName)}
        disabled={!providers}
      >
        {PROVIDER_NAMES.map((name) => {
          const info = options.find((p) => p.name === name);
          const available = info?.available ?? false;
          const model = info?.model ? ` (${info.model})` : "";
          return (
            <option key={name} value={name} disabled={!available} title={info?.detail}>
              {PROVIDER_LABELS[name]}
              {model}
              {available ? "" : " - unavailable"}
            </option>
          );
        })}
      </select>
    </label>
  );
}
