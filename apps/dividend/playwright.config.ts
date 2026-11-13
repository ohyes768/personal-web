import { defineConfig } from '@playwright/test';

// 默认打 3003（本机 next dev 或容器里的构建）；端口被别的实例占用时，
// 用 E2E_BASE_URL 指到那个已经跑着的实例，避免起第二个 dev server 抢 .next。
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3003';
// 本机没下到与 @playwright/test 版本匹配的 chromium 时，用系统 Chrome 跑：
//   E2E_CHROME=/usr/bin/google-chrome npx playwright test
const chrome = process.env.E2E_CHROME;

export default defineConfig({
  testDir: './e2e',
  use: {
    baseURL,
    ...(chrome ? { launchOptions: { executablePath: chrome } } : {}),
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
      command: 'node node_modules/next/dist/bin/next dev -p 3003',
      url: 'http://127.0.0.1:3003',
      reuseExistingServer: true,
    },
});
