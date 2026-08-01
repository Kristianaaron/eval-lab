import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Dev: proxy API calls to the FastAPI backend (default `eval-lab serve` port).
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8100",
    },
  },
  build: {
    outDir: "dist",
  },
});
