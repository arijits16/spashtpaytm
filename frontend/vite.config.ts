import { fileURLToPath } from "node:url";

// `vitest/config` re-exports Vite's defineConfig widened with the `test` block.
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * Vite config for the Spasht frontend.
 *
 * The dev server proxies `/api` to the FastAPI backend on 8000, so the phone
 * needs only one HTTPS tunnel in phase 12 and there is no CORS in development.
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // Mirrors the `@/*` paths entry in tsconfig.app.json.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    // Phase 12 adds the tunnel host here; Vite blocks unknown Host headers.
    allowedHosts: [".ngrok-free.app", ".trycloudflare.com"],
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5173,
    allowedHosts: [".ngrok-free.app", ".trycloudflare.com"],
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
