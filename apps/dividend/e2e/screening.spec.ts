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

/** quality 场景控制：测试内直接改 perCode / 开关 failQuery，route handler 每次读最新值 */
interface QualityScenario {
  perCode: Record<string, Record<string, unknown>>;
  jobStatus?: string;
  failQuery?: { value: boolean };
  analyzeCalls?: string[][];
  /** mount 重新发现用的最新任务；未设置时返回 null */
  latestJob?: Record<string, unknown> | null;
}

function perCodeItem(state: string, extra: Record<string, unknown> = {}) {
  return { state, error: state === 'failed' ? 'run 终态 failed' : null, updated_at: '2026-10-29T10:00:00+08:00', name: '测试公司', ...extra };
}

async function setup(page: Page, initiallyFavorite = false, analysisDuration?: number | null, quality?: QualityScenario) {
  let codes: string[] = initiallyFavorite ? [stock.code] : [];
  let batchAttempts = 0;
  await page.route('**/api/dividend/**', async route => {
    const url = new URL(route.request().url());
    const favorites = () => ({ version: 1, total: codes.length, codes, items: codes.map(code => ({ code, added_at: '2026-10-09' })), notify: { enabled: false, rules: [], last_notified_at: null } });
    if (url.pathname.endsWith('/stocks/screen')) {
      const conditions = route.request().postDataJSON();
      const extra = quality ? [
        { stock: { ...stock, code: '000002', name: '排队公司' }, status: 'eligible', reasons: [], warnings: [] },
        { stock: { ...stock, code: '000003', name: '空闲公司' }, status: 'eligible', reasons: [], warnings: [] },
      ] : [];
      await route.fulfill({ json: { conditions, items: [
        { stock, status: 'eligible', reasons: [], warnings: ['一个季度扣非利润同比下降，建议持续关注'] },
        ...extra,
        { stock: { ...stock, code: '000009', name: '资料不足', roe_avg_3y: null }, status: 'insufficient_data', reasons: ['连续三年年度 ROE 数据缺失'], warnings: [] },
      ], counts: { eligible: quality ? 3 : 1, excluded: 0, insufficient_data: 1 }, dividend_years: [2023, 2024, 2025], total: quality ? 4 : 2, last_updated: null } });
    } else if (url.pathname.endsWith('/favorites/batch')) {
      batchAttempts++;
      const requested = route.request().postDataJSON().codes as string[];
      const items = requested.map(code => ({ code, status: batchAttempts === 1 ? 'failed' : codes.includes(code) ? 'already_exists' : 'added', error: batchAttempts === 1 ? '写入失败' : undefined }));
      if (batchAttempts > 1) codes = [...new Set([...codes, ...requested])];
      await route.fulfill({ json: { items, favorites: favorites() } });
    } else if (url.pathname.includes('/favorites/alerts')) await route.fulfill({ json: { items: [], total: 0, enabled_count: 0 } });
    else if (url.pathname.endsWith('/quality/analyze')) {
      quality?.analyzeCalls?.push(route.request().postDataJSON().codes as string[]);
      await route.fulfill({ json: { job_id: 'job-1', kind: 'quality', status: quality?.jobStatus ?? 'running', total: 3, processed: 0, succeeded: 0, failed: 0, remaining: 3, codes: route.request().postDataJSON().codes, failed_codes: [], retry_codes: [], error: null, finished_at: null, message: '', per_code: quality?.perCode ?? {} } });
    }
    else if (url.pathname.includes('/quality/jobs/')) {
      if (quality?.failQuery?.value) { await route.fulfill({ status: 500, json: { detail: '查询评级进度失败' } }); return; }
      await route.fulfill({ json: { job_id: 'job-1', kind: 'quality', status: quality?.jobStatus ?? 'running', total: 3, processed: 0, succeeded: 0, failed: 0, remaining: 3, codes: ['000001', '000002', '000003'], failed_codes: [], retry_codes: [], error: null, finished_at: null, message: '', per_code: quality?.perCode ?? {} } });
    }
    else if (url.pathname.endsWith('/refresh/jobs')) await route.fulfill({ json: quality?.latestJob !== undefined ? quality.latestJob : null });
    else if (url.pathname.endsWith('/quality')) await route.fulfill({ json: { total: 1, hermes_configured: true, per_code: quality?.perCode ?? {}, scores: {
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
  await expect(page.getByRole('cell', { name: /资料不足\s+000009/ })).toBeVisible();
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
  // 重评后全局进度在评级弹框内可见
  await page.getByRole('button', { name: '重评' }).last().click();
  await expect(page.getByText(/评级任务进行中/)).toBeVisible();
  await expect(page.getByRole('heading', { name: '基本面评级 · 测试公司（000001）', exact: true })).toBeVisible();
});

test('quality queue shows running and queued stocks, keeps others actionable, and ticks elapsed time', async ({ page }) => {
  const startedAt = new Date(Date.now() - 125_000).toISOString();
  const quality: QualityScenario = {
    perCode: { '000001': perCodeItem('running', { started_at: startedAt, queued_at: startedAt }) },
  };
  await setup(page, false, undefined, quality);
  await page.goto('/?tab=screening');
  await expect(page.getByRole('button', { name: '符合条件 3' })).toBeVisible();
  // 提交 000001 后出现队列面板：running 行带实时计时
  await page.getByRole('button', { name: '分析', exact: true }).first().click();
  const queue = page.getByLabel('评级任务队列');
  await expect(queue).toBeVisible();
  await expect(queue.getByText(/已分析 2分\d+秒/)).toBeVisible();
  // 追加 000002：同一任务排队；面板显示运行+排队计数
  quality.perCode['000002'] = perCodeItem('queued', { queued_at: new Date().toISOString(), name: '排队公司' });
  await expect(queue.getByText(/运行 1 · 排队 1/)).toBeVisible({ timeout: 10_000 });
  await expect(queue.getByText('排队中…')).toBeVisible();
  // 运行中/排队中股票行内显示状态文本而非按钮，空闲股票 000003 仍可点击
  await expect(page.getByRole('button', { name: '重评', exact: true })).toHaveCount(0);
  // 000001 评级中、000002 排队中都是状态文本；只有空闲的 000003 还有按钮且可点
  await expect(page.getByRole('button', { name: '分析', exact: true })).toHaveCount(1);
  await expect(page.getByRole('button', { name: '分析', exact: true })).toBeEnabled();
  // 计时持续走（本地每秒刷新，不依赖轮询、不因轮询重置）
  const firstElapsed = await queue.getByText(/已分析 2分\d+秒/).textContent();
  await page.waitForTimeout(2100);
  const secondElapsed = await queue.getByText(/已分析 2分\d+秒/).textContent();
  expect(secondElapsed).not.toEqual(firstElapsed);
});

test('quality queue recovers after reload and offers retry for failed stock', async ({ page }) => {
  const quality: QualityScenario = {
    perCode: {
      '000001': perCodeItem('failed', { started_at: new Date(Date.now() - 200_000).toISOString(), finished_at: new Date(Date.now() - 100_000).toISOString() }),
      '000002': perCodeItem('queued', { queued_at: new Date().toISOString(), name: '排队公司' }),
    },
    latestJob: { job_id: 'job-1', kind: 'quality', status: 'running', total: 3, processed: 0, succeeded: 0, failed: 1, remaining: 2, codes: ['000001', '000002', '000003'], failed_codes: ['000001'], retry_codes: ['000001', '000002'], error: null, finished_at: null, message: '' },
    analyzeCalls: [],
  };
  await setup(page, false, undefined, quality);
  await page.goto('/?tab=screening');
  const queue = page.getByLabel('评级任务队列');
  // 刷新恢复：mount 发现 running 任务恢复轮询，面板展示失败与排队项
  await expect(queue).toBeVisible({ timeout: 10_000 });
  await expect(queue.getByText(/失败 · 耗时/)).toBeVisible();
  await expect(queue.getByText('排队中…')).toBeVisible();
  // 行内重试把失败股票追加重新提交
  await queue.getByRole('button', { name: '重试', exact: true }).click();
  await expect.poll(() => quality.analyzeCalls?.[0]).toEqual(['000001']);
});

test('temporary quality query errors keep state and recover automatically', async ({ page }) => {
  const startedAt = new Date(Date.now() - 30_000).toISOString();
  const quality: QualityScenario = {
    perCode: { '000001': perCodeItem('running', { started_at: startedAt, queued_at: startedAt }) },
    failQuery: { value: false },
  };
  await setup(page, false, undefined, quality);
  await page.goto('/?tab=screening');
  await page.getByRole('button', { name: '分析', exact: true }).first().click();
  const queue = page.getByLabel('评级任务队列');
  await expect(queue).toBeVisible();
  // 查询开始失败：状态保留并提示自动重试
  quality.failQuery.value = true;
  await expect(page.getByText('评级进度查询失败，任务不受影响，自动重试中…')).toBeVisible({ timeout: 10_000 });
  await expect(queue.getByText(/已分析/)).toBeVisible(); // 面板与计时不受影响
  // 恢复后提示消失
  quality.failQuery.value = false;
  await expect(page.getByText('评级进度查询失败，任务不受影响，自动重试中…')).toHaveCount(0, { timeout: 10_000 });
});
