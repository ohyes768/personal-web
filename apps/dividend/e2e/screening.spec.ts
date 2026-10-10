import { expect, test, type Page } from '@playwright/test';

const stock = {
  code: '000001', name: '测试公司', exchange: '深市主板', avg_yield_3y: 4,
  dividend_2023: 1, dividend_2024: 1, dividend_2025: 1,
  roe: 12, roe_year: 2025, roe_avg_3y: 11,
  roe_history: [{ year: 2023, value: 10 }, { year: 2024, value: 11 }, { year: 2025, value: 12 }],
  net_profit_ex_non_recurring_yoy: 2, latest_quarter_label: '2026Q2', latest_quarter_yoy_pct: -1,
  previous_quarter_label: '2026Q1', previous_quarter_yoy_pct: 2,
};

async function setup(page: Page, initiallyFavorite = false) {
  let codes: string[] = initiallyFavorite ? [stock.code] : [];
  let batchAttempts = 0;
  await page.route('**/api/dividend/**', async route => {
    const url = new URL(route.request().url());
    const favorites = () => ({ version: 1, total: codes.length, codes, items: codes.map(code => ({ code, added_at: '2026-10-09' })), notify: { enabled: false, rules: [], last_notified_at: null } });
    if (url.pathname.endsWith('/stocks/screen')) {
      const conditions = route.request().postDataJSON();
      await route.fulfill({ json: { conditions, items: [
        { stock, status: 'eligible', reasons: [], warnings: ['一个季度扣非利润同比下降，建议持续关注'] },
        { stock: { ...stock, code: '000002', name: '资料不足', roe_avg_3y: null }, status: 'insufficient_data', reasons: ['连续三年年度 ROE 数据缺失'], warnings: [] },
      ], counts: { eligible: 1, excluded: 0, insufficient_data: 1 }, dividend_years: [2023, 2024, 2025], total: 2, last_updated: null } });
    } else if (url.pathname.endsWith('/favorites/batch')) {
      batchAttempts++;
      const requested = route.request().postDataJSON().codes as string[];
      const items = requested.map(code => ({ code, status: batchAttempts === 1 ? 'failed' : codes.includes(code) ? 'already_exists' : 'added', error: batchAttempts === 1 ? '写入失败' : undefined }));
      if (batchAttempts > 1) codes = [...new Set([...codes, ...requested])];
      await route.fulfill({ json: { items, favorites: favorites() } });
    } else if (url.pathname.includes('/favorites/alerts')) await route.fulfill({ json: { items: [], total: 0, enabled_count: 0 } });
    else if (url.pathname.endsWith('/favorites')) await route.fulfill({ json: favorites() });
    else if (url.pathname.endsWith('/stocks')) await route.fulfill({ json: { items: url.searchParams.get('min_yield') === '0' ? [stock] : [], total: 0 } });
    else if (url.pathname.endsWith('/stats')) await route.fulfill({ json: { total_stocks: 2 } });
    else if (url.pathname.endsWith('/m120')) await route.fulfill({ json: { items: [], total: 0 } });
    else await route.fulfill({ json: { needs_update: false, missing_codes: [], days_since_update: 0 } });
  });
}

test('screening remains accessible with no stocks in old filter, allows retrying failed favorite', async ({ page }) => {
  await setup(page);
  await page.goto('/?tab=screening');
  await expect(page.getByRole('heading', { name: '选出值得持续关注的公司' })).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: '近三年平均 ROE ≥' })).toHaveValue('10');
  await expect(page.getByText('一个季度扣非利润同比下降，建议持续关注')).toBeVisible();
  await page.screenshot({ path: '/private/tmp/dividend-screening.png', fullPage: true });
  await page.getByRole('button', { name: '收藏全部符合条件' }).click();
  await expect(page.getByRole('status')).toContainText('失败 1 只');
  await page.getByRole('button', { name: '重试失败项' }).click();
  await expect(page.getByRole('status')).toContainText('新增 1 只');
  await expect(page.getByRole('cell', { name: '已收藏', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '待补数据 1' }).click();
  await expect(page.getByRole('cell', { name: '资料不足 000002', exact: true })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '勾选 资料不足' })).toBeDisabled();
});

test('conditions persist, query uses configured ROE and reset restores defaults', async ({ page }) => {
  await setup(page);
  await page.goto('/?tab=screening');
  await expect(page.getByRole('button', { name: '符合条件 1' })).toBeVisible();
  const average = page.getByRole('spinbutton', { name: '近三年平均 ROE ≥' });
  await average.fill('12');
  const request = page.waitForRequest(req => req.url().endsWith('/stocks/screen') && req.method() === 'POST' && req.postDataJSON().min_roe_avg_3y === 12);
  await page.getByRole('button', { name: '查询候选' }).click();
  expect((await request).postDataJSON().min_roe_avg_3y).toBe(12);
  await page.reload();
  await expect(average).toHaveValue('12');
  await page.getByRole('button', { name: '恢复默认' }).click();
  await expect(average).toHaveValue('10');
});

test('legacy watchlist link displays favorites outside current dividend filter', async ({ page }) => {
  await setup(page, true);
  await page.goto('/?tab=watchlist');
  await expect(page.getByRole('cell', { name: /测试公司/ }).first()).toBeVisible();
  await page.getByRole('button', { name: '选股关注', exact: true }).click();
  await expect(page).toHaveURL(/tab=screening/);
});
