import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against the Home Assistant container from `docker-compose.yml`.
 *
 *   cd tests/e2e && docker compose up -d && npx playwright test
 *
 * `reuseExistingServer` semantics are not applicable here: the container is
 * started by the caller so a failed run leaves the instance around for
 * `--debug` and for reading `.storage`.
 */
export default defineConfig({
  testDir: "./specs",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./harness/global-setup.ts",
  use: {
    baseURL: process.env["HA_URL"] ?? "http://localhost:8123",
    trace: "retain-on-failure",
    video: "off",
    screenshot: "only-on-failure",
    actionTimeout: 20_000,
    navigationTimeout: 60_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
