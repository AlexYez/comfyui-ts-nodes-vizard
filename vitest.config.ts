import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["ui/src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    setupFiles: ["ui/src/test/setup.ts"]
  }
});
