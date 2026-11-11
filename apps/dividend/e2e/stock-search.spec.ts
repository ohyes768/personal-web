import { expect, test, type Page } from '@playwright/test';

/** 默认「全部」列表（阈值内） */
const baseStocks = [{
  code: '600900', name: '长江电力', exchange: '沪市主板',
  avg_yield_3y: 4.28, dividend_2023: 0.75, dividend_2024: 0.85, dividend_2025: 0.94,
}];

/** 搜索命中的股票：低于阈值（默认列表里没有） */
const searchedStock = {
  code: '000333', name: '美的集团', exchange: '深市主板',
  avg_yield_3y: 2.1, dividend_2023: 1.0, dividend_2024: 1.2, dividend_2025: 1.3,
};

interface StocksRequest {
  search: string | null;
  codes: string | null;
  minYield: string | null;
}

async function setup(page: Page, initialFavorites: string[] = []) {
  const stockRequests: StocksRequest[] = [];
  let favorites = [...initialFavorites];
  const favoritePayload = () => ({
    version: 1,
    total: favorites.length,
    codes: favorites,
    items: favorites.map(code => ({ code, added_at: '2026-11-11' })),
    notify: { enabled: false, rules: [], last_notified_at: null },
  });

  await page.route('**/api/dividend/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path.endsWith('/stocks') && request.method() === 'GET') {
      const search = url.searchParams.get('search');
      stockRequests.push({
        search,
        codes: url.searchParams.get('codes'),
        minYield: url.searchParams.get('min_yield'),
      });
      const items = search ? (search.includes('美的') ? [searchedStock] : []) : baseStocks;
      await route.fulfill({ json: { total: items.length, items, last_updated: null } });
      return;
    }
    if (path.endsWith('/favorites/alerts/status')) {
      await route.fulfill({ json: { items: [], total: 0, enabled_count: 0 } });
      return;
    }
    if (path.endsWith('/favorites') && request.method() === 'GET') {
      await route.fulfill({ json: favoritePayload() });
      return;
    }
    if (path.includes('/favorites/') && request.method() === 'POST') {
      const code = path.split('/').pop() ?? '';
      favorites = [...new Set([...favorites, code])];
      await route.fulfill({ json: favoritePayload() });
      return;
    }
    if (path.includes('/favorites/') && request.method() === 'DELETE') {
      const code = path.split('/').pop() ?? '';
      favorites = favorites.filter(item => item !== code);
      await route.fulfill({ json: favoritePayload() });
      return;
    }
    if (path.endsWith('/stats')) {
      await route.fulfill({ json: { total_stocks: 202 } });
      return;
    }
    if (path.endsWith('/m120')) {
      await route.fulfill({ json: { total: 2, items: [
        { code: '600900', name: '长江电力', m120: 25.8, close: 26.1, deviation: 1.2, realtime: 26.2, realtime_deviation: 1.5, yield_ttm: 3.4, pe: 18, pb: 2.6 },
        { code: '000333', name: '美的集团', m120: 60.1, close: 61.0, deviation: 1.5, realtime: 61.2, realtime_deviation: 1.8, yield_ttm: 2.2, pe: 12, pb: 2.1 },
      ] } });
      return;
    }
    if (path.endsWith('/prices')) {
      await route.fulfill({ json: { total: 0, items: [] } });
      return;
    }
    if (path.includes('/refresh/jobs')) {
      await route.fulfill({ status: 404, json: { detail: '暂无任务' } });
      return;
    }
    await route.fulfill({ json: { needs_update: false, missing_codes: [], days_since_update: 0, total: 0, items: [] } });
  });

  return { stockRequests, favoriteCodes: () => favorites };
}

test('搜索命中阈值外的已收集股票，可直接点星标收藏', async ({ page }) => {
  const { stockRequests } = await setup(page);
  await page.goto('/');
  await expect(page.getByText('长江电力')).toBeVisible();

  await page.getByRole('searchbox', { name: '搜索股票名称或代码' }).fill('美的');

  // 请求带上 search，且不带股息率阈值筛选
  await expect.poll(() => stockRequests.filter(r => r.search === '美的').length).toBeGreaterThan(0);
  const searchRequest = stockRequests.find(r => r.search === '美的')!;
  expect(searchRequest.minYield).toBe('0');

  // 命中结果出现，默认阈值列表被替换
  await expect(page.getByText('美的集团')).toBeVisible();
  await expect(page.getByText('长江电力')).toHaveCount(0);

  // 搜索结果可直接收藏
  await page.getByRole('button', { name: '收藏 美的集团' }).click();
  await expect(page.getByRole('button', { name: '取消收藏 美的集团' })).toBeVisible();
});

test('搜索无匹配时显示明确空状态，不做全市场搜索', async ({ page }) => {
  await setup(page);
  await page.goto('/');

  await page.getByRole('searchbox', { name: '搜索股票名称或代码' }).fill('不存在的公司');
  await expect(page.getByText('没有找到匹配的已收集股票')).toBeVisible();
  await expect(page.getByText(/未收集的股票不会出现在这里/)).toBeVisible();
  await expect(page.getByText(/202 只已收集股票/)).toBeVisible();
});

test('清空搜索恢复原有过滤行为', async ({ page }) => {
  await setup(page);
  await page.goto('/');

  const searchbox = page.getByRole('searchbox', { name: '搜索股票名称或代码' });
  await searchbox.fill('美的');
  await expect(page.getByText('美的集团')).toBeVisible();

  await page.getByRole('button', { name: '清除搜索', exact: true }).click();
  await expect(page.getByText('长江电力')).toBeVisible();
  await expect(page.getByText('美的集团')).toHaveCount(0);
});

test('只看收藏时搜索限定在收藏范围内', async ({ page }) => {
  const { stockRequests } = await setup(page, ['000333']);
  await page.goto('/?fav=1');

  await page.getByRole('searchbox', { name: '搜索股票名称或代码' }).fill('美的');
  await expect.poll(() => stockRequests.some(r => r.search === '美的')).toBe(true);
  const searchRequest = stockRequests.find(r => r.search === '美的')!;
  expect(searchRequest.codes).toBe('000333');
});
