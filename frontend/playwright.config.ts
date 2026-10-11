import { defineConfig } from "@playwright/test";

export default defineConfig({ testDir: "./tests/e2e", workers: 1,
  reporter: "list", outputDir: "../.private/playwright-results",
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3010", trace: "off", screenshot: "off" } });
