/**
 * 估值资料阅读页（独立路由 /valuation-reader）e2e
 *
 * 覆盖：报告正文渲染、下拉换篇、上一篇/下一篇、返回主页面还原视图、
 * 非 ready 报告只读（不给应用按钮）、已应用与待应用的提示。
 */
import { expect, test } from '@playwright/test';
import { scenario, setup } from './tracking-fixture';

test('valuation reader renders the report and flips between companies', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/valuation-reader?code=000001&fromTab=alerts');

  await expect(page.getByRole('heading', { name: '估值资料阅读' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '测试公司' })).toBeVisible();
  await expect(page.getByText('四点均有公司级依据')).toBeVisible();
  // 摘要与估值依据正文都在（正文里的 md 也有同名标题，按层级取章节标题）
  await expect(page.getByRole('heading', { name: '估值依据', level: 3 })).toBeVisible();

  // 阅读集合 = 有报告的股票（000001 / 600000 / 600005），没有报告的 600004 不在集合里
  const select = page.getByLabel('选择股票');
  await expect(select).toBeVisible();
  await expect(select.locator('option')).toHaveCount(3);
  await expect(page.getByText('第 1 / 3 篇').first()).toBeVisible();

  // 下一篇：切到 600000（资料不足，报告只读）
  await page.getByRole('button', { name: '下一篇' }).click();
  await expect(page.getByRole('heading', { name: '暂停公司' })).toBeVisible();
  await expect(page.getByText('第 2 / 3 篇').first()).toBeVisible();
  await expect(page.getByText('核心材料不足，暂不出价')).toBeVisible();
  // 非 ready 报告不给应用按钮
  await expect(page.getByRole('button', { name: /应用挡位/ })).toHaveCount(0);

  // 上一篇：回到第一篇
  await page.getByRole('button', { name: '上一篇' }).click();
  await expect(page.getByRole('heading', { name: '测试公司' })).toBeVisible();
  await expect(page).toHaveURL(/code=000001/);
});

test('valuation reader dropdown switches the current company', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/valuation-reader?fromTab=alerts');
  // 没有 code 时落到第一篇
  await expect(page.getByRole('heading', { name: '测试公司' })).toBeVisible();
  await expect(page).toHaveURL(/code=000001/);

  await page.getByLabel('选择股票').selectOption('600005');
  await expect(page.getByRole('heading', { name: '缺口公司' })).toBeVisible();
  await expect(page).toHaveURL(/code=600005/);
});

test('valuation reader returns to the list view it came from', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/valuation-reader?code=000001&fromTab=alerts');
  const back = page.getByRole('link', { name: '← 返回股息率' });
  await expect(back).toHaveAttribute('href', '/?tab=alerts');
  await back.click();
  await expect(page).toHaveURL(/\?tab=alerts/);
});

test('a pending report shows the apply action and the not-yet-applied hint', async ({ page }) => {
  const s = scenario();
  // 000001：报告（11-11）新于生效挡位（11-01）→ 待应用
  await setup(page, s);
  await page.goto('/valuation-reader?code=000001&fromTab=alerts');
  await expect(page.getByText('这份评估还没有应用')).toBeVisible();
  await expect(page.getByRole('button', { name: '应用挡位' })).toBeVisible();
  // 点应用走同一张紧凑确认卡
  await page.getByRole('button', { name: '应用挡位' }).click();
  const confirmDialog = page.getByRole('heading', { name: '确认应用挡位 · 测试公司' }).locator('../..');
  await expect(confirmDialog).toBeVisible();
  await expect(confirmDialog.getByText('¥8.50')).toBeVisible();
  await confirmDialog.getByTestId('valuation-confirm-apply-button').click();
  await expect(s.applyCalls).toEqual([{ code: '000001', evaluated_at: '2026-11-11T10:00:00' }]);
});

test('valuation reader offers the session download for the report', async ({ page }) => {
  const s = scenario();
  s.reports['000001'] = { ...s.reports['000001']!, run_id: 'run-reader-1' };
  await setup(page, s);
  await page.route('**/api/dividend/valuation/runs/run-reader-1/session', route => route.fulfill({
    status: 200,
    contentType: 'text/markdown; charset=utf-8',
    body: '# Hermes run 会话记录：run-reader-1\n\n## 消息记录（1 条）\n',
  }));
  await page.goto('/valuation-reader?code=000001&fromTab=alerts');
  const button = page.getByRole('button', { name: '下载会话记录' });
  await expect(button).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await button.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('hermes-run-reader-1-session.md');
});
