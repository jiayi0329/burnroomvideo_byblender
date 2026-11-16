import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './e2e-live',
  workers: 1,
  timeout: 90000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'msedge',
    headless: true,
    viewport: { width: 1600, height: 1000 },
  },
})
