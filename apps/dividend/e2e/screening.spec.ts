import { expect, test, type Page } from '@playwright/test';

const stock = {
  code: '000001', name: '测试公司', exchange: '深市主板', avg_yield_3y: 4,
  dividend_2023: 1, dividend_2024: 1, dividend_2025: 1,
  roe: 12, roe_year: 2025, roe_avg_3y: 11,
  roe_history: [{ year: 2023, value: 10 }, { year: 2024, value: 11 }, { year: 2025, value: 12 }],
  annual_net_profit_ex_non_recurring: 120000000, annual_profit_year: 2025,
  net_profit_ex_non_recurring_yoy: 2, latest_quarter_label: '2026Q2', latest_quarter_yoy_pct: -1,
  previous_quarter_label: '2026Q1', previous_quarter_yoy_pct: 2,
};

async function setup(page: Page, initiallyFavorite = false, analysisDuration?: number | null) {
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
    else if (url.pathname.endsWith('/quality/analyze')) await route.fulfill({ json: { job_id: 'job-1', kind: 'quality', status: 'running', total: 1, processed: 0, succeeded: 0, failed: 0, remaining: 1, failed_codes: [], retry_codes: [], error: null, finished_at: null, message: '' } });
    else if (url.pathname.includes('/quality/jobs/')) await route.fulfill({ json: { job_id: 'job-1', kind: 'quality', status: 'running', total: 1, processed: 0, succeeded: 0, failed: 0, remaining: 1, failed_codes: [], retry_codes: [], error: null, finished_at: null, message: '' } });
    else if (url.pathname.endsWith('/quality')) await route.fulfill({ json: { total: 1, hermes_configured: true, scores: {
      '000001': { code: '000001', name: '测试公司', dimensions: { business: 4, moat: 4, industry: 3, management: 3, financial: 5 }, weighted_score: 3.7, stars: 3, boundary: null, summary: '示例摘要', risks: [], watch_points: [], report_md: '## 评级报告\n\n示例正文。', scored_at: '2026-10-20 10:00', data_date: '2026-10-20', analysis_duration_seconds: analysisDuration },
    } } });
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
  await page.getByRole('button', { name: '收藏全部符合条件' }).click();
  await expect(page.getByRole('status')).toContainText('失败 1 只');
  await page.getByRole('button', { name: '重试失败项' }).click();
  await expect(page.getByRole('status')).toContainText('新增 1 只');
  await expect(page.getByRole('cell', { name: '已收藏', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '待补数据 1' }).click();
  await expect(page.getByRole('cell', { name: /资料不足\s+000002/ })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '勾选 资料不足' })).toBeDisabled();
  // 单季下滑警告不再占据列表列，进入个股详情弹层后展示
  await page.getByRole('button', { name: '符合条件 1' }).click();
  await page.getByRole('button', { name: /测试公司/ }).click();
  await expect(page.getByRole('heading', { name: '测试公司（000001）', exact: true })).toBeVisible();
  await expect(page.getByText('一个季度扣非利润同比下降，建议持续关注')).toBeVisible();
});

for (const [duration, label] of [
  [155.25, '2分35秒'],
  [3600, '1小时0分0秒'],
  [0, '0秒'],
  [undefined, '未记录'],
  [null, '未记录'],
] as const) {
  test(`rating report shows analysis duration: ${duration}`, async ({ page }) => {
    await setup(page, false, duration);
    await page.goto('/?tab=screening');
    await page.getByRole('button', { name: '3.7', exact: true }).click();
    await expect(page.getByText(`分析耗时 ${label}`, { exact: false })).toBeVisible();
  });
}

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


test('legacy saved conditions default decline to 30 and keep previous thresholds', async ({ page }) => {
  await setup(page);
  await page.addInitScript(() => localStorage.setItem('dividend-screening-conditions-v1', JSON.stringify({ min_yield: 4.5, min_roe: 13, min_roe_avg_3y: 12, exchange: '沪市主板' })));
  const request = page.waitForRequest(req => req.url().endsWith('/stocks/screen') && req.method() === 'POST');
  await page.goto('/?tab=screening');
  expect((await request).postDataJSON()).toMatchObject({ min_yield: 4.5, min_roe: 13, min_roe_avg_3y: 12, exchange: '沪市主板', max_quarter_profit_decline_pct: 30 });
  await expect(page.getByRole('spinbutton', { name: '单季扣非利润最大降幅' })).toHaveValue('30');
});

test('decline threshold marks changed snapshot, persists, rejects zero, and resets', async ({ page }) => {
  await setup(page);
  await page.goto('/?tab=screening');
  await expect(page.getByRole('button', { name: '符合条件 1' })).toBeVisible();
  const decline = page.getByRole('spinbutton', { name: '单季扣非利润最大降幅' });
  await decline.fill('20');
  await expect(page.getByText('条件已修改，当前仍显示上次查询结果，请点击「查询候选」。')).toBeVisible();
  const request = page.waitForRequest(req => req.url().endsWith('/stocks/screen') && req.method() === 'POST' && req.postDataJSON().max_quarter_profit_decline_pct === 20);
  await page.getByRole('button', { name: '查询候选' }).click();
  expect((await request).postDataJSON().max_quarter_profit_decline_pct).toBe(20);
  await expect(page.getByText('条件已修改，当前仍显示上次查询结果，请点击「查询候选」。')).toHaveCount(0);
  await page.reload();
  await expect(decline).toHaveValue('20');
  await decline.fill('0');
  await expect(page.getByRole('button', { name: '查询候选' })).toBeDisabled();
  await decline.fill('50');
  const resetRequest = page.waitForRequest(req => req.url().endsWith('/stocks/screen') && req.method() === 'POST' && req.postDataJSON().max_quarter_profit_decline_pct === 30);
  await page.getByRole('button', { name: '恢复默认' }).click();
  await resetRequest;
  await expect(decline).toHaveValue('30');
  expect(await page.evaluate(() => localStorage.getItem('dividend-screening-conditions-v1'))).toBeNull();
});

test('rating column shows weighted score, row click opens detail without rating entry', async ({ page }) => {
  await setup(page);
  await page.goto('/?tab=screening');
  await expect(page.getByRole('button', { name: '符合条件 1' })).toBeVisible();
  // 评级结果列展示加权分（一位小数），点击打开评级弹框
  await expect(page.getByRole('button', { name: '3.7', exact: true })).toBeVisible();
  // 点行打开个股详情弹层，六个区块齐备
  await page.getByRole('button', { name: /测试公司/ }).click();
  await expect(page.getByRole('heading', { name: '测试公司（000001）', exact: true })).toBeVisible();
  for (const block of ['筛选状态', '股息率', '盈利质量', '买点参考', '筹码']) {
    await expect(page.getByRole('heading', { level: 3, name: new RegExp(block) })).toBeVisible();
  }
  // 详情弹层内不提供基本面评级入口（后续统一加）
  await expect(page.getByRole('button', { name: /基本面评级/ })).toHaveCount(0);
});

test('reanalyze inside rating modal shows progress and rating modal stays open', async ({ page }) => {
  await setup(page);
  await page.goto('/?tab=screening');
  // 评级结果列打开评级弹框（与详情弹层互斥）
  await page.getByRole('button', { name: '3.7', exact: true }).click();
  await expect(page.getByRole('heading', { name: '基本面评级 · 测试公司（000001）', exact: true })).toBeVisible();
  // 重评后进度在评级弹框内可见
  await page.getByRole('button', { name: '重评' }).last().click();
  await expect(page.getByText(/评级分析中/)).toBeVisible();
  await expect(page.getByRole('heading', { name: '基本面评级 · 测试公司（000001）', exact: true })).toBeVisible();
});
