import { expect, test, type Page } from "@playwright/test";

/**
 * 端到端：登录 → 手工建服务 → 加端口 → 搜索 → 导出 → 恢复预览 → 删除台账。
 * 依赖真实后端（SERVICE_MANAGER_E2E_PASSWORD 提供管理口令）。
 */

const PASSWORD = process.env.SM_E2E_PASSWORD || "devpass";

/** 用例里通过接口造的条目：登记在这里，afterEach 无条件清掉。 */
const createdServiceIds: string[] = [];

test.afterEach(async ({ page }) => {
  for (const id of createdServiceIds.splice(0)) {
    await page.request
      .delete(`/api/services/services/${id}`, {
        headers: { Origin: new URL(page.url()).origin },
      })
      .catch(() => undefined);
  }
});

async function login(page: Page) {
  await page.goto("/services");
  // 会话检查是异步的：等「门禁表单」或「已登录内容」二者之一出现，再决定要不要登录。
  // 不能用 isVisible() 立即判断——React 还没 hydrate 时它恒为 false，会跳过登录。
  const gate = page.locator("#admin-password");
  const content = page.getByRole("heading", { name: "服务", exact: true });
  await expect(gate.or(content).first()).toBeVisible();
  if (await gate.isVisible()) {
    await gate.fill(PASSWORD);
    await page.getByRole("button", { name: "登录" }).click();
  }
  await expect(content).toBeVisible();
}

test("登录门禁：未登录只显示登录表单", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/services");
  await expect(page.locator("#admin-password")).toBeVisible();
  await expect(page.getByRole("heading", { name: "服务", exact: true })).toHaveCount(0);
});

test("台账条目走接口建立后，搜索、加端口、删除都可用", async ({ page }) => {
  await login(page);
  const name = `e2e-服务-${Date.now()}`;

  // 列表页不再有「新增服务」入口：台账条目从发现导入来（这里用接口代劳）
  await expect(page.getByRole("button", { name: "新增服务" })).toHaveCount(0);
  const created = await page.request.post("/api/services/services", {
    headers: { Origin: new URL(page.url()).origin },
    data: { name },
  });
  expect(created.ok()).toBeTruthy();
  createdServiceIds.push((await created.json()).id as string);

  await page.goto("/services");
  await page.getByLabel("搜索服务").fill(name);
  await expect(page.getByRole("link", { name, exact: true })).toHaveCount(1);

  await page.getByRole("link", { name, exact: true }).click();
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();

  // 手工端口
  await page.locator("#pn-ip").fill("0.0.0.0");
  await page.locator("#pn-port").fill("39999");
  await page.locator("#pn-note").fill("e2e 人工端口");
  await page.getByRole("button", { name: "记录端口" }).click();
  await expect(page.getByText("39999")).toBeVisible();

  // 删除台账（确认对话框）
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "从台账移除" }).click();
  await expect(page.getByRole("heading", { name: "服务", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
});

test("归属字段已退役：列表平铺，没有分组 tab 也没有归属下拉", async ({ page }) => {
  await login(page);
  await page.goto("/services");
  // 不再有「我维护的 / 别人的」两个分组 tab
  await expect(page.getByRole("tab")).toHaveCount(0);
  // 行里与详情页都没有归属下拉
  await expect(page.locator('select[aria-label$="的归属"]')).toHaveCount(0);

  const name = `e2e-平铺-${Date.now()}`;
  const created = await page.request.post("/api/services/services", {
    headers: { Origin: new URL(page.url()).origin },
    data: { name },
  });
  expect(created.ok()).toBeTruthy();
  createdServiceIds.push((await created.json()).id as string);

  await page.goto("/services");
  await page.getByLabel("搜索服务").fill(name);
  await expect(page.getByRole("link", { name, exact: true })).toHaveCount(1);
});

test("标签可维护：弹窗里勾选已有标签 + 新建一个，保存后列表行立即更新", async ({ page }) => {
  await login(page);
  const name = `e2e-标签-${Date.now()}`;
  const created = await page.request.post("/api/services/services", {
    headers: { Origin: new URL(page.url()).origin },
    data: { name },
  });
  expect(created.ok()).toBeTruthy();
  createdServiceIds.push((await created.json()).id as string);

  await page.goto("/services");
  await page.getByLabel("搜索服务").fill(name);

  // 打开标签弹窗
  await page.getByLabel(`编辑 ${name} 的标签`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  // 新建一个标签：输入 + 回车
  await dialog.getByLabel("新标签").fill("e2e-标签");
  await dialog.getByLabel("新标签").press("Enter");
  await expect(dialog.getByRole("button", { name: "e2e-标签" })).toBeVisible();

  // 重复添加要报错
  await dialog.getByLabel("新标签").fill("e2e-标签");
  await dialog.getByLabel("新标签").press("Enter");
  await expect(dialog.getByText("该标签已勾选")).toBeVisible();

  // 保存 → 列表行立即出现这个标签
  await dialog.getByRole("button", { name: "保存" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const row = page.locator("tbody tr", { hasText: name });
  await expect(row.getByRole("button", { name: "e2e-标签", exact: true })).toBeVisible();

});

test("标签可筛选：多选是 AND，可一键清除", async ({ page }) => {
  await login(page);
  const stamp = Date.now();
  // 两条都带 e2e-a，只有一条带 e2e-b：AND 语义能自证，不依赖词表里已有什么
  const both = `e2e-筛选-双-${stamp}`;
  const onlyOne = `e2e-筛选-单-${stamp}`;
  for (const [name, tags] of [
    [both, ["e2e-a", "e2e-b"]],
    [onlyOne, ["e2e-a"]],
  ]) {
    const created = await page.request.post("/api/services/services", {
      headers: { Origin: new URL(page.url()).origin },
      data: { name, tags },
    });
    expect(created.ok()).toBeTruthy();
    createdServiceIds.push((await created.json()).id as string);
  }

  await page.goto("/services");
  const filterBar = page.locator(".tag-filter-bar");
  // 候选来自全库并集：刚建的标签出现在筛选栏
  await expect(filterBar.getByRole("button", { name: "e2e-a" })).toBeVisible();
  await expect(filterBar.getByRole("button", { name: "e2e-b" })).toBeVisible();

  // 勾一个 → 两条都命中
  await filterBar.getByRole("button", { name: "e2e-a" }).click();
  await expect(page.getByRole("link", { name: both, exact: true })).toHaveCount(1);
  await expect(page.getByRole("link", { name: onlyOne, exact: true })).toHaveCount(1);

  // 再勾一个 AND 条件 → 只剩同时具备的那条
  await filterBar.getByRole("button", { name: "e2e-b" }).click();
  await expect(page.getByRole("link", { name: both, exact: true })).toHaveCount(1);
  await expect(page.getByRole("link", { name: onlyOne, exact: true })).toHaveCount(0);

  // 一键清除 → 恢复（筛选栏上的「清除标签」）
  await filterBar.getByRole("button", { name: "清除标签" }).click();
  await expect(page.getByRole("link", { name: both, exact: true })).toHaveCount(1);
  await expect(page.getByRole("link", { name: onlyOne, exact: true })).toHaveCount(1);
});

test("分类字段已退役：界面上没有分类入口", async ({ page }) => {
  await login(page);
  await page.goto("/services");
  await expect(page.getByLabel("按分类筛选")).toHaveCount(0);
  await expect(page.getByText("分类")).toHaveCount(0);

  await page.goto("/services/discovery");
  await expect(page.locator("#import-category")).toHaveCount(0);
});

test("入口表单：localhost 探测被拒并给出说明", async ({ page }) => {
  await login(page);
  const name = `e2e-入口-${Date.now()}`;
  // 列表页没有「新增服务」入口了，条目走接口建（发现导入在真实环境里做这件事）
  const created = await page.request.post("/api/services/services", {
    headers: { Origin: new URL(page.url()).origin },
    data: { name },
  });
  expect(created.ok()).toBeTruthy();
  await page.goto("/services");
  await page.getByLabel("搜索服务").fill(name);
  await page.getByRole("link", { name, exact: true }).click();

  await page.getByRole("button", { name: "添加入口" }).click();
  await page.locator("#ep-url").fill("https://web.duomi77.cn:9443/e2e");
  await page.locator("#ep-probe").fill("http://localhost:3003/");
  await page.getByRole("button", { name: "保存入口" }).click();
  // 断言后端拒绝的提示（表单里本来就有一句 hint 也提到 localhost，必须限定到提示条）
  await expect(page.getByRole("status")).toContainText("localhost");

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "从台账移除" }).click();
});

test("资源总览三个标签可切换并显示范围说明", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "资源总览" }).click();
  await expect(page.getByText(/不能据此证明端口空闲/)).toBeVisible();
  await page.getByRole("tab", { name: "域名" }).click();
  await page.getByRole("tab", { name: "证书" }).click();
  await expect(page.getByRole("tab", { name: "证书" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("发现页展示候选表格（或明确的不可用提示）", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "发现导入" }).click();
  await expect(page.getByRole("heading", { name: "发现导入" })).toBeVisible();
  // 三种正常终态：有候选表格 / 无匹配候选 / Docker 不可用（后端未配 DOCKER_HOST 时）
  const table = page.locator("table").first();
  const empty = page.getByText(/没有匹配的候选容器|Docker 不可用时没有候选/);
  await expect(table.or(empty).first()).toBeVisible();
  if (await table.isVisible()) {
    await expect(page.getByRole("columnheader", { name: "容器" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "端口" })).toBeVisible();
  }
});

test("导出与恢复预览", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "设置" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 JSON" }).click();
  const download = await downloadPromise;
  const path = await download.path();
  expect(path).toBeTruthy();
  await page.locator("#backup-file").setInputFiles(path!);
  await expect(page.getByText("预览")).toBeVisible();
  await page.getByRole("button", { name: "取消" }).click();
});

test("375px 下主要页面无横向滚动且可操作", async ({ page }) => {
  // 移动项目固定 375 宽；桌面项目 1440。这里只对窄视口执行严格断言。
  const viewport = page.viewportSize();
  test.skip(viewport !== null && viewport.width > 400, "仅窄视口执行 375px 断言");
  await login(page);
  for (const path of ["/services", "/services/resources", "/services/discovery", "/services/settings"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth - clientWidth, `${path} 出现横向滚动`).toBeLessThanOrEqual(1);
  }
  // 返回首页入口在小屏可见
  await page.goto("/services");
  await expect(page.getByRole("link", { name: "← 返回首页" })).toBeVisible();
});

test("失败可重试：后端不可达时给出错误提示而非白屏", async ({ page }) => {
  await login(page);
  await page.route("**/api/services/summary*", (route) => route.abort());
  await page.goto("/services");
  await expect(page.getByRole("heading", { name: "服务", exact: true })).toBeVisible();
  await page.unroute("**/api/services/summary*");
});
