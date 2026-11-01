import {
  MODEL_NAMES,
  type ModelName,
  type ProviderInfo,
  type ProviderName,
  type ProvidersResponse,
} from "../types";

export const PROVIDER_LABELS: Record<string, string> = {
  auto: "Default",
  anthropic: "Anthropic",
  ollama_gpu: "Ollama GPU",
  ollama: "Ollama",
  mock: "Mock",
};

// The models, under a heading for where they run.
const MODEL_GROUPS: { label: string; models: ModelName[] }[] = [
  { label: "Cloud LLM", models: ["anthropic"] },
  { label: "Local LLM", models: ["ollama_gpu", "ollama"] },
];

function info(providers: ProvidersResponse | null, name: string): ProviderInfo | undefined {
  return providers?.providers.find((p) => p.name === name);
}

/**
 * The model "Default" will try first: the user's default model if it's
 * available, otherwise the next available one in the backend's order
 * (Anthropic, Ollama GPU, Ollama). null while nothing is known or available.
 */
export function resolveDefault(
  providers: ProvidersResponse | null,
  defaultModel: ModelName,
): ModelName | null {
  const order = [defaultModel, ...MODEL_NAMES.filter((m) => m !== defaultModel)];
  return order.find((m) => info(providers, m)?.available) ?? null;
}

function defaultLabel(providers: ProvidersResponse | null, defaultModel: ModelName): string {
  if (!providers) return "Default";
  const used = resolveDefault(providers, defaultModel);
  if (used === null) return "Default (no model available)";
  if (used === defaultModel) return `Default (${PROVIDER_LABELS[used]})`;
  return `Default (${PROVIDER_LABELS[used]}, ${PROVIDER_LABELS[defaultModel]} unavailable)`;
}

/** <optgroup>s of models, each named with its model and marked if unavailable. */
function ModelOptions({
  providers,
  disableUnavailable,
}: {
  providers: ProvidersResponse | null;
  disableUnavailable: boolean;
}) {
  return MODEL_GROUPS.map((group) => (
    <optgroup key={group.label} label={group.label}>
      {group.models.map((name) => {
        const model = info(providers, name);
        const available = model?.available ?? false;
        return (
          <option
            key={name}
            value={name}
            disabled={disableUnavailable && !available}
            title={model?.detail}
          >
            {PROVIDER_LABELS[name]}
            {model?.model ? ` (${model.model})` : ""}
            {available ? "" : " - unavailable"}
          </option>
        );
      })}
    </optgroup>
  ));
}

interface ProviderSelectProps {
  providers: ProvidersResponse | null;
  value: ProviderName;
  onChange: (provider: ProviderName) => void;
  /** The user's default model, shown in brackets after "Default". */
  defaultModel: ModelName;
}

/**
 * Which model answers in this chat: "Default" (the user's default model,
 * falling back to the others if it's down) or one model exactly.
 * Models the backend reports as unavailable are disabled.
 */
export function ProviderSelect({ providers, value, onChange, defaultModel }: ProviderSelectProps) {
  return (
    <label className="provider">
      Model
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as ProviderName)}
        disabled={!providers}
      >
        <option value="auto" title="Your default model, falling back to the others if it fails">
          {defaultLabel(providers, defaultModel)}
        </option>
        <ModelOptions providers={providers} disableUnavailable />
      </select>
    </label>
  );
}

interface DefaultModelSelectProps {
  providers: ProvidersResponse | null;
  value: ModelName;
  onChange: (model: ModelName) => void;
}

/**
 * The model "Default" uses. Unavailable models can still be chosen (say,
 * Ollama GPU before it's set up); Default then uses the next one.
 */
export function DefaultModelSelect({ providers, value, onChange }: DefaultModelSelectProps) {
  return (
    <label className="provider">
      Default model
      <select value={value} onChange={(e) => onChange(e.target.value as ModelName)}>
        <ModelOptions providers={providers} disableUnavailable={false} />
      </select>
    </label>
  );
}
