import { expect, test } from '@playwright/test';

test('restores progress after reload and reports partial failure with retry', async ({ page }) => {
  let finished = false;
  await page.route('**/api/dividend/**', async route => {
    const url = route.request().url();
    const job = { job_id: 'job-1', kind: 'm120', status: finished ? 'partial_failed' : 'running', total: 2,
      processed: finished ? 2 : 1, succeeded: 1, failed: finished ? 1 : 0, remaining: finished ? 0 : 1,
      retry_codes: ['000090'], failed_codes: finished ? ['000090'] : [], error: null,
      finished_at: finished ? '2026-10-12T15:00:00+08:00' : null };
    const body = url.includes('/refresh/jobs') ? (url.includes('financial') ? null : job)
      : url.includes('/stocks') ? { total: 1, items: [{ code: '000090', name: '天健集团', avg_yield_3y: 4 }] }
      : url.includes('/stats') ? { total_stocks: 1 }
      : url.includes('/favorites/alerts') ? { items: [] }
      : url.includes('/favorites') ? { codes: [], items: [] }
      : url.includes('/m120/status') ? { needs_update: true, missing_codes: ['000090'] }
      : url.includes('/m120') ? { total: 0, items: [] }
      : { needs_update: false, missing_codes: [] };
    await route.fulfill({ json: body });
  });
  await page.goto('/');
  await page.getByRole('button', { name: /数据更新/ }).click();
  await expect(page.getByText('已处理 1/2，成功 1，失败 0，未处理 1')).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: /数据更新/ }).click();
  await expect(page.getByText('已处理 1/2，成功 1，失败 0，未处理 1')).toBeVisible();
  finished = true;
  await expect(page.getByText('部分失败')).toBeVisible();
  await expect(page.getByRole('button', { name: '重试失败和未处理股票' })).toBeVisible();
});

test('acceptance keeps browsing available and query failure recovers', async ({ page }) => {
  let accepted = false;
  let offline = false;
  const job = { job_id: 'job-2', kind: 'm120', status: 'running', total: 2, processed: 0,
    succeeded: 0, failed: 0, remaining: 2, retry_codes: ['000090', '600000'], failed_codes: [], error: null };
  await page.route('**/api/dividend/**', async route => {
    const url = route.request().url();
    if (url.includes('/m120/refresh')) {
      accepted = true;
      return route.fulfill({ status: 202, json: { ...job, reused: true } });
    }
    if (url.includes('/refresh/jobs') && offline && !url.includes('financial')) return route.abort();
    const body = url.includes('/refresh/jobs') ? (accepted && !url.includes('financial') ? job : null)
      : url.includes('/stocks') ? { total: 1, items: [{ code: '000090', name: '天健集团', avg_yield_3y: 4 }] }
      : url.includes('/stats') ? { total_stocks: 1 }
      : url.includes('/favorites/alerts') ? { items: [] }
      : url.includes('/favorites') ? { codes: [], items: [] }
      : url.includes('/m120/status') ? { needs_update: true, missing_codes: ['000090'] }
      : url.includes('/m120') ? { total: 0, items: [] }
      : { needs_update: false, missing_codes: [] };
    await route.fulfill({ json: body });
  });
  await page.goto('/');
  await page.getByRole('button', { name: /数据更新/ }).click();
  const drawer = page.getByRole('complementary', { name: '数据更新' });
  await drawer.locator('div').filter({ hasText: /^M120 均线/ }).first().getByRole('button', { name: '更新', exact: true }).click();
  await expect(page.getByText('已有同类任务，继续显示当前进度')).toBeVisible();
  offline = true;
  await expect(page.getByText(/暂时无法查询进度/)).toBeVisible({ timeout: 10000 });
  await expect(drawer.getByRole('button', { name: '更新中', exact: true })).toBeDisabled();
  await drawer.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(drawer).not.toBeVisible();
  await page.getByRole('button', { name: /数据更新/ }).click();
  offline = false;
  await expect(page.getByText(/暂时无法查询进度/)).not.toBeVisible({ timeout: 10000 });
  await expect(page.getByText('已处理 0/2，成功 0，失败 0，未处理 2')).toBeVisible();
  await page.screenshot({ path: '../../.tmp/dividend-refresh-progress.png', fullPage: true });
});
