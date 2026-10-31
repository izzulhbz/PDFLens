/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev mode: the Vite dev server forwards /api to Flask, so the browser sees
// one origin, exactly like Nginx does in Docker. Same-origin means the
// session cookie just works and no CORS is needed.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:5000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  build: {
    // No source maps in the production bundle served by Nginx.
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    restoreMocks: true,
  },
});
