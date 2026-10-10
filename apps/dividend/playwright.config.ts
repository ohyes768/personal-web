import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:3003' },
  webServer: {
    command: 'node node_modules/next/dist/bin/next dev -p 3003',
    url: 'http://127.0.0.1:3003',
    reuseExistingServer: true,
  },
});
