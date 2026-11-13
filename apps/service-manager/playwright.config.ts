import { defineConfig, devices } from "@playwright/test";

/** e2e 针对真实测试后端（8102）+ 真实前端（3012）；外部探测用后端 fixture。 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.SM_E2E_BASE_URL || "http://127.0.0.1:3012",
    // 指到 nginx 入口（https://…:9443，自签证书）跑生产拓扑时用；直连 3012 不受影响
    ignoreHTTPSErrors: true,
    trace: "off",
    screenshot: "off",
  },
  // PRD A11 要求 375px 与 1440px 两档；Desktop Chrome 默认只有 1280×720，
  // 这里显式钉到 1440×900，避免「测的是 1280 却报 1440 通过」。
  // 用宿主机已安装的 Chrome：本机无法下载 Playwright 自带 Chromium（缓存目录只读 + CDN 不可达）
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        channel: "chrome",
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "mobile",
      use: { viewport: { width: 375, height: 812 }, channel: "chrome" },
    },
  ],
});
