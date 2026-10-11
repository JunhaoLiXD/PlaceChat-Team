import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // Resolve the "@/*" alias from tsconfig.json.
    tsconfigPaths: true,
  },
  test: {
    environment: "jsdom",
    // The default "forks" pool times out on some Windows setups; threads work everywhere.
    pool: "threads",
  },
});
