// Unmount rendered components and clear storage between tests, so tests
// can't affect each other. (Testing Library only does the first part on its
// own when Vitest globals are enabled; this project imports them explicitly.)
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
