import { defineConfig, devices } from "@playwright/test";

// Runs against a live stack: `make dev` (web :3000 + API :8000 + database) must be up.
export default defineConfig({
  testDir: "./e2e",
  timeout: 240_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, testIgnore: /mobile/ },
    { name: "mobile", use: { ...devices["Pixel 7"], viewport: { width: 375, height: 812 } }, testMatch: /mobile/ },
  ],
});
