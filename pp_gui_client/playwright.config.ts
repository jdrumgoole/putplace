import { defineConfig } from '@playwright/test';
import path from 'path';

/**
 * Playwright configuration for PutPlace Electron Client E2E tests.
 *
 * Uses the electron package to launch the app and tests against the dev server.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 1800000, // 30 minutes per test (can be overridden via CLI: --timeout=<ms>)
  expect: {
    timeout: 30000, // 30 seconds for expect assertions
  },
  fullyParallel: false, // Run tests sequentially for Electron
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // Single worker for Electron tests
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
});
