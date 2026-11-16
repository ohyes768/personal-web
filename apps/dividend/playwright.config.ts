import { defineConfig } from '@playwright/test';
import { execSync } from 'node:child_process';

// 默认打 3003（本机 next dev）；端口被占用时，用 E2E_BASE_URL 指到那个实例，
// 避免起第二个 dev server 抢 .next。
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3003';
// 本机没下到与 @playwright/test 版本匹配的 chromium 时，用系统 Chrome 跑：
//   E2E_CHROME=/usr/bin/google-chrome npx playwright test
const chrome = process.env.E2E_CHROME;

/**
 * 3003 上跑的是不是 docker 生产容器（dividend-frontend）？
 *
 * reuseExistingServer 本意是复用本机 next dev（跑的是当前工作区代码），
 * 但 3003 也可能被部署容器占着——容器里是上次部署的旧构建，拿它跑 e2e
 * 会把未提交改动「验证成失败」（2026-11-16 实际踩过：源码已删的文案，
 * 容器 SSR 里还在，测试一直红）。
 *
 * 判据：docker port 映射 3003 → 视为容器，不复用；此时 webServer 仍会尝试
 * 起 dev server，但端口被容器占着起不来。所以容器在场时必须显式给
 * E2E_BASE_URL（打容器或别的端口），否则直接报错拦下来。
 */
function isDockerContainerOnPort(port: number): boolean {
  try {
    const out = execSync(`docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null`, { encoding: 'utf8' });
    return out.split('\n').some(line => line.includes(`:${port}->`));
  } catch {
    return false; // docker 不可用（未安装/无守护进程）时按本机环境处理
  }
}

if (!process.env.E2E_BASE_URL && isDockerContainerOnPort(3003)) {
  throw new Error(
    '端口 3003 被 docker 容器（dividend-frontend）占用，复用它跑 e2e 会打到旧构建。\n'
    + '验证未部署改动：先临时停容器（docker compose stop dividend-frontend）再跑，\n'
    + '或显式指定 E2E_BASE_URL 打向其他 dev server。',
  );
}

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
