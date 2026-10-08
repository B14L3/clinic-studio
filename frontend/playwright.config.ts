import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // diagnostic.spec.ts hits the live Gemini API and is a manual-use-only
  // diagnostic tool, not part of the deterministic CI suite.
  testIgnore: ["**/diagnostic.spec.ts"],
  fullyParallel: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
    headless: true,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
