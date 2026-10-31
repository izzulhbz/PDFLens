import { useCallback, useState } from "react";

import { PROVIDER_NAMES, type ProviderName } from "./types";

export const PROVIDER_STORAGE_KEY = "pdflens.provider";

function readStored(): ProviderName {
  try {
    const stored = window.localStorage.getItem(PROVIDER_STORAGE_KEY);
    // localStorage can be edited by hand, so only accept known values.
    if (stored && (PROVIDER_NAMES as readonly string[]).includes(stored)) {
      return stored as ProviderName;
    }
  } catch {
    // Storage can be blocked (private mode, strict settings): just use the default.
  }
  return "auto";
}

/** The provider chosen in the dropdown, remembered across visits in localStorage. */
export function useStoredProvider(): [ProviderName, (provider: ProviderName) => void] {
  const [provider, setProvider] = useState<ProviderName>(readStored);

  const choose = useCallback((next: ProviderName) => {
    setProvider(next);
    try {
      window.localStorage.setItem(PROVIDER_STORAGE_KEY, next);
    } catch {
      // Not remembered, but the choice still applies for this visit.
    }
  }, []);

  return [provider, choose];
}
