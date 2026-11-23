import { defineConfig } from '@playwright/test';

/**
 * E2E against the running stack. Start it first:
 *   docker compose up -d --build   (frontend on :5173, backend on :8010)
 * or run the Vite dev server with BILLING_API_TARGET pointing at the backend.
 * Install browsers once: npx playwright install chromium
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    headless: true,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
