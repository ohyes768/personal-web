import { expect, test } from '@playwright/test';

const stocks = [{
  code: '600900', name: '长江电力', exchange: '沪市主板',
  avg_yield_3y: 4.28, dividend_2025: 0.94,
}];

test('opens data update drawer and exposes scheduler settings', async ({ page }) => {
  await page.route('**/api/dividend/**', async route => {
    const url = route.request().url();
    const body = url.includes('/stocks') ? { total: 1, items: stocks }
      : url.includes('/stats') ? { total_stocks: 1 }
      : url.includes('/m120') ? { total: 1, items: [] }
      : url.includes('/favorites/alerts') ? { items: [], total: 0, enabled_count: 0 }
      : url.includes('/favorites') ? { codes: [], items: [], total: 0 }
      : { needs_update: false, missing_codes: [], days_since_update: 0 };
    await route.fulfill({ json: body });
  });

  await page.goto('/');
  await page.getByRole('button', { name: /数据更新/ }).click();
  await expect(page.getByRole('complementary', { name: '数据更新' })).toBeVisible();
  await expect(page.getByRole('button', { name: '自动更新设置' })).toBeVisible();
});
