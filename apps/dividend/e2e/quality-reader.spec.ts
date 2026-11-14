import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * 基本面资料阅读页 E2E
 *
 * 约定：所有 /api/dividend/quality 写接口（analyze / jobs / queue）一律拦截并断言调用次数为 0，
 * 绝不真实触发分析（收费且耗时）。
 */

interface ScoreFixture {
  code: string;
  name: string;
  skill_version?: string | null;
  dimensions: Record<string, number | null>;
  weighted_score: number | null;
  stars: number | null;
  boundary: string | null;
  summary: string;
  risks: string[];
  watch_points: string[];
  report_md: string;
  scored_at: string;
  data_date: string;
  analysis_duration_seconds?: number | null;
}

function score(partial: Partial<ScoreFixture> & { code: string; name: string }): ScoreFixture {
  return {
    skill_version: '4.4.0',
    dimensions: { business: 4, moat: 4, industry: 3, management: 3, financial: 5 },
    weighted_score: 3.7,
    stars: 3,
    boundary: null,
    summary: '业务模式清晰，护城河稳固。',
    risks: ['原料价格波动'],
    watch_points: ['关注季度扣非利润'],
    report_md: '## 业务验证\n\n公司以制造业为主，客户集中度中等。',
    scored_at: '2026-11-01 10:00',
    data_date: '2026-10-30',
    analysis_duration_seconds: 155.25,
    ...partial,
  };
}

const THREE_SCORES: Record<string, ScoreFixture> = {
  '000002': score({ code: '000002', name: '乙公司' }),
  '000001': score({
    code: '000001', name: '甲公司',
    dimensions: { business: 4, moat: 4, industry: 3, management: 3, financial: null },
    weighted_score: null, stars: null, boundary: null,
    summary: '灰色地带（证据不足，未评级）',
    report_md: '',
  }),
  '000003': score({ code: '000003', name: '丙公司', report_md: '## 业务验证\n\n正常报告正文。' }),
};

interface ScreeningCheckFixture {
  key: string;
  label: string;
  result: 'pass' | 'fail' | 'missing' | 'warn';
  value_text: string;
  threshold_text: string;
  detail: string;
  reason: string;
  warning: string;
}

/** 单股筛选复核响应；000002 有一条不符，用来验证阅读页的标识 */
function screeningFixture(code: string) {
  const failing = code === '000002';
  const checks: ScreeningCheckFixture[] = [
    {
      key: 'yield_3y', label: '近三年平均股息率', result: failing ? 'fail' : 'pass',
      value_text: failing ? '4.29%' : '5.10%', threshold_text: '≥ 5%',
      detail: failing ? '低于门槛 5%，需复核' : '', reason: failing ? '近三年平均股息率低于 5%' : '', warning: '',
    },
    {
      key: 'roe', label: '最近年度 ROE', result: 'pass', value_text: '16.66%', threshold_text: '≥ 10%',
      detail: '', reason: '', warning: '',
    },
  ];
  return {
    code,
    name: code === '000002' ? '乙公司' : '甲公司',
    status: failing ? 'excluded' : 'eligible',
    reasons: failing ? ['近三年平均股息率低于 5%'] : [],
    warnings: [],
    checks,
    conditions: { min_yield: 5, min_roe: 10, min_roe_avg_3y: 10, max_quarter_profit_decline_pct: 30, min_cagr_3y: 0 },
    last_updated: '2026-11-01T10:00:00+08:00',
    financial_last_updated: '2026-10-30T10:00:00+08:00',
  };
}

interface QualityApiState {
  scores: Record<string, ScoreFixture>;
  hermesConfigured: boolean;
  currentSkillVersion: string | null;
  /** 第几次请求（0 起）后开始失败 */
  failFromRequest?: number;
  requestCount: number;
  /** 单股筛选复核是否返回失败 */
  screeningFails?: boolean;
  /** 记录被拦截的写接口调用 */
  writeCalls: string[];
}

async function setupQualityApi(page: Page, state: QualityApiState) {
  await page.route('**/api/dividend/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    // 写接口一律拦截并记录；阅读页不应触发任何写操作
    if (method !== 'GET' || url.pathname.includes('/quality/analyze') || url.pathname.includes('/quality/jobs') || url.pathname.includes('/quality/queue')) {
      state.writeCalls.push(`${method} ${url.pathname}`);
      await route.fulfill({ status: 500, json: { detail: '测试禁止写接口' } });
      return;
    }
    if (url.pathname.endsWith('/quality')) {
      state.requestCount += 1;
      if (state.failFromRequest !== undefined && state.requestCount > state.failFromRequest) {
        await route.fulfill({ status: 500, json: { detail: '读取基本面资料失败' } });
        return;
      }
      await route.fulfill({
        json: {
          total: Object.keys(state.scores).length,
          hermes_configured: state.hermesConfigured,
          current_skill_version: state.currentSkillVersion,
          per_code: { '000009': { state: 'queued', error: null, updated_at: '2026-11-01 10:00', position: 1 } },
          scores: state.scores,
        },
      });
      return;
    }
    // 单股筛选复核（只读 GET）
    if (url.pathname.endsWith('/screening')) {
      if (state.screeningFails) {
        await route.fulfill({ status: 500, json: { detail: '筛选复核失败' } });
        return;
      }
      const code = url.pathname.split('/').slice(-2)[0];
      await route.fulfill({ json: screeningFixture(code) });
      return;
    }
    // 批量筛选状态（下拉列表标注用；与单股复核同一套 fixture 判定）
    if (url.pathname.endsWith('/screen/statuses')) {
      if (state.screeningFails) {
        await route.fulfill({ status: 500, json: { detail: '筛选状态失败' } });
        return;
      }
      await route.fulfill({ json: {
        items: Object.keys(state.scores).map(code => ({ code, status: screeningFixture(code).status })),
        total: Object.keys(state.scores).length,
        conditions: { min_yield: 5, min_roe: 10, min_roe_avg_3y: 10, max_quarter_profit_decline_pct: 30, min_cagr_3y: 0 },
      } });
      return;
    }
    await route.fulfill({ json: {} });
  });
}

function newState(overrides: Partial<QualityApiState> = {}): QualityApiState {
  return {
    scores: THREE_SCORES,
    hermesConfigured: true,
    currentSkillVersion: '4.4.0',
    requestCount: 0,
    writeCalls: [],
    ...overrides,
  };
}

test('reader lists saved reports by code, keeps null dimension as 未评分 and hides aggregate stars', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  // 按代码升序：000001 甲公司 / 000002 乙公司 / 000003 丙公司；无下拉筛选，默认固定第一篇
  await expect(page.getByText('第 1 / 3 篇').first()).toBeVisible();
  // null 维度显示未评分；不显示总星级/加权分/边界横幅
  await expect(page.getByText('未评分').first()).toBeVisible();
  await expect(page.getByText('3.7', { exact: true })).toHaveCount(0);
  await expect(page.getByText('⭐')).toHaveCount(0);
  await expect(page.getByText('踩线')).toHaveCount(0);
  // 正文为空时给出提示，其余结构仍可读
  await expect(page.getByText('暂无完整报告正文')).toBeVisible();
  await expect(page.getByText('数据日期 2026-10-30')).toBeVisible();
  await expect(page.getByText('分析耗时 2分35秒')).toBeVisible();
  expect(state.writeCalls).toEqual([]);
});

test('prev/next navigation syncs company, body, progress and URL', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();

  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await expect(page).toHaveURL(/code=000002/);
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  await expect(page.getByText('第 2 / 3 篇').first()).toBeVisible();

  await page.getByRole('button', { name: '上一篇', exact: true }).click();
  await expect(page).toHaveURL(/code=000001/);
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();

  // 连续翻到第三篇
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await expect(page).toHaveURL(/code=000003/);
  await expect(page.getByRole('heading', { name: '丙公司', exact: true })).toBeVisible();
  expect(state.writeCalls).toEqual([]);
});

test('first and last article disable the matching nav button', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByRole('button', { name: '上一篇', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '下一篇', exact: true })).toBeEnabled();
  await page.goto('/quality-reader?code=000003');
  await expect(page.getByRole('button', { name: '下一篇', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '上一篇', exact: true })).toBeEnabled();
});

test('only one article disables both nav buttons', async ({ page }) => {
  const state = newState({ scores: { '000001': THREE_SCORES['000001'] } });
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByRole('button', { name: '上一篇', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '下一篇', exact: true })).toBeDisabled();
});

test('unknown code shows unavailable state and does not silently show another company', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=999999');
  await expect(page.getByText('该公司的基本面资料暂不可用')).toBeVisible();
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '下一篇', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '上一篇', exact: true })).toBeDisabled();
});

test('empty result set shows empty state instead of an error', async ({ page }) => {
  const state = newState({ scores: {} });
  await setupQualityApi(page, state);
  await page.goto('/quality-reader');
  await expect(page.getByText('暂无基本面资料')).toBeVisible();
  await expect(page.getByText('加载失败')).toHaveCount(0);
});

test('read failure shows retry and never pretends the collection is empty', async ({ page }) => {
  const state = newState({ failFromRequest: 0 });
  await setupQualityApi(page, state);
  await page.goto('/quality-reader');
  await expect(page.getByText(/基本面资料加载失败/)).toBeVisible();
  await expect(page.getByText('暂无基本面资料')).toHaveCount(0);
  // 重试成功后恢复正文
  state.failFromRequest = undefined;
  await page.getByRole('button', { name: '重试' }).click();
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
});

test('refresh failure keeps previous content and reports the error', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000002');
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  state.failFromRequest = state.requestCount;
  await page.getByRole('button', { name: '刷新资料' }).click();
  await expect(page.getByText(/刷新失败/)).toBeVisible();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
});

test('refresh keeps the selected code, ignores newly added reports and detects deleted ones', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000002');
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();

  // 新增更小代码的报告：当前篇不变
  state.scores = { ...state.scores, '000000': score({ code: '000000', name: '零零公司' }) };
  await page.getByRole('button', { name: '刷新资料' }).click();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();

  // 当前公司被删除：进入不存在状态，不擅自跳到邻篇
  const { '000002': _removed, ...rest } = state.scores;
  state.scores = rest;
  await page.getByRole('button', { name: '刷新资料' }).click();
  await expect(page.getByText('该公司的基本面资料暂不可用')).toBeVisible();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toHaveCount(0);
});

test('browser back and forward restore the company from the URL', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
});

test('reading works even when Hermes is not configured', async ({ page }) => {
  const state = newState({ hermesConfigured: false });
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000002');
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
});

test('reader never calls quality write endpoints', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await page.getByRole('button', { name: '刷新资料' }).click();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  expect(state.writeCalls).toEqual([]);
});

test('reader marks the screening conditions the company does not meet', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000002');
  await expect(page.getByRole('heading', { name: '筛选条件复核' })).toBeVisible();
  await expect(page.getByText('未符合', { exact: true })).toBeVisible();
  await expect(page.getByText('不符 · 需复核')).toBeVisible();
  await expect(page.getByText('1 项不符合，需复核')).toBeVisible();
  // 原因来自后端判定，原样展示
  await expect(page.getByText('近三年平均股息率低于 5%')).toBeVisible();
  // 门槛与当前值都在表里，阅读时可直接对照
  await expect(page.getByText('近三年平均股息率').first()).toBeVisible();
  await expect(page.getByText('4.29%')).toBeVisible();
  await expect(page.getByText('≥ 5%')).toBeVisible();
});

test('reader keeps the screening verdict of the company being read', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByText('符合条件', { exact: true })).toBeVisible();
  await expect(page.getByText('不符 · 需复核')).toHaveCount(0);
  // 换篇后复核结论跟着换，不残留上一篇的不符项
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  await expect(page.getByText('未符合', { exact: true })).toBeVisible();
  await expect(page.getByText('不符 · 需复核')).toHaveCount(1);
});

test('reading still works when the screening verdict cannot be loaded', async ({ page }) => {
  const state = newState({ screeningFails: true });
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  await expect(page.getByText(/筛选复核加载失败/)).toBeVisible();
  // 状态映射同样失败：下拉不显示标记，但选择功能正常
  const select = page.getByRole('combobox', { name: '选择股票' });
  await expect(select).toBeEnabled();
  await expect(select.locator('option')).toHaveCount(3);
});

test('company select marks each option with its screening status', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  const select = page.getByRole('combobox', { name: '选择股票' });
  await expect(select.locator('option')).toHaveCount(3);
  // ✓ 符合 / ✗ 未符合：与面板判定同源
  await expect(select.locator('option').filter({ hasText: '甲公司' })).toHaveText(/✓/);
  await expect(select.locator('option').filter({ hasText: '乙公司' })).toHaveText(/✗/);
  await expect(select.locator('option').filter({ hasText: '乙公司' })).toHaveText(/未符合/);
  await expect(select.locator('option').filter({ hasText: '丙公司' })).toHaveText(/✓/);
});

test('reader layout does not overflow horizontally on phone and desktop', async ({ page }, testInfo) => {
  const state = newState({
    scores: {
      '000001': score({
        code: '000001', name: '甲公司',
        report_md: [
          '## 业务验证',
          '超长链接 https://example.com/' + 'a'.repeat(200) + ' 结束',
          '',
          '| 列一 | 列二 | 列三 | 列四 | 列五 | 列六 | 列七 | 列八 | 列九 | 列十 | 列十一 | 列十二 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |',
          '| 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 | 十二列宽表格内容 |',
          '',
          '```',
          'const veryLongLine = "' + 'x'.repeat(300) + '";',
          '```',
          '',
          '末段标记',
        ].join('\n'),
      }),
    },
  });
  await setupQualityApi(page, state);
  for (const viewport of [{ width: 360, height: 800 }, { width: 390, height: 844 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/quality-reader?code=000001');
    await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
    // 表格容器局部横滑
    const tableScroll = await page.evaluate(() => {
      const wrap = document.querySelector('.quality-reader-md .quality-reader-table-wrap') as HTMLElement | null;
      return wrap ? { scrollWidth: wrap.scrollWidth, clientWidth: wrap.clientWidth } : null;
    });
    if (tableScroll) expect(tableScroll.scrollWidth).toBeGreaterThan(tableScroll.clientWidth);
    await page.screenshot({ path: testInfo.outputPath(`reader-${viewport.width}x${viewport.height}.png`), fullPage: true });
  }
});

test('last paragraph is not hidden behind the fixed bottom navigation', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/quality-reader?code=000002');
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const visible = await page.evaluate(() => {
    const nav = document.querySelector('.quality-reader-nav') as HTMLElement | null;
    const article = document.querySelector('.quality-reader-article') as HTMLElement | null;
    if (!nav || !article) return null;
    const navTop = nav.getBoundingClientRect().top;
    const articleBottom = article.getBoundingClientRect().bottom;
    return { navTop, articleBottom };
  });
  expect(visible).not.toBeNull();
  if (visible) expect(visible.articleBottom).toBeLessThanOrEqual(visible.navTop + 1);
});

test('first load without a code writes the canonical code into the URL', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  await expect(page).toHaveURL(/code=000001/);
});

test('an empty code parameter is treated as an unavailable report, not as the first one', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=');
  await expect(page.getByText('该公司的基本面资料暂不可用')).toBeVisible();
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toHaveCount(0);
});

test('rapid next clicks advance one article each time', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  const next = page.getByRole('button', { name: '下一篇', exact: true });
  await next.click();
  await next.click();
  await expect(page).toHaveURL(/code=000003/);
  await expect(page.getByRole('heading', { name: '丙公司', exact: true })).toBeVisible();
  await expect(page.getByText('第 3 / 3 篇').first()).toBeVisible();
});

test('switching articles scrolls back to the top while refreshing does not', async ({ page }) => {
  const longBody = Array.from({ length: 40 }, (_, i) => `第 ${i + 1} 段正文，用于制造可滚动的长文阅读场景。`).join('\n\n');
  const state = newState({
    scores: {
      '000001': score({ code: '000001', name: '甲公司', report_md: longBody }),
      '000002': score({ code: '000002', name: '乙公司', report_md: longBody }),
      '000003': score({ code: '000003', name: '丙公司', report_md: longBody }),
    },
  });
  await setupQualityApi(page, state);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/quality-reader?code=000002');
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 400));
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
  // 刷新资料不改变滚动位置，也不抢焦点
  // （用 in-page click，避免 Playwright 点击顶部按钮时自动滚动到按钮）
  await page.evaluate(() => {
    const button = Array.from(document.querySelectorAll('button')).find(node => node.textContent?.trim() === '刷新资料');
    (button as HTMLButtonElement | undefined)?.click();
  });
  await page.waitForTimeout(400);
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
  expect(await page.evaluate(() => document.activeElement?.className ?? '')).not.toContain('quality-reader-company');
  // 主动换篇回到顶部
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await expect(page.getByRole('heading', { name: '丙公司', exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});

test('reader never polls for analysis jobs and only reads the scores endpoint', async ({ page }) => {
  const paths: string[] = [];
  await page.route('**/api/dividend/**', async route => {
    const url = new URL(route.request().url());
    paths.push(`${route.request().method()} ${url.pathname}${url.search}`);
    if (url.pathname.endsWith('/quality')) {
      await route.fulfill({ json: { total: 1, hermes_configured: true, current_skill_version: '4.4.0', scores: {
        '000001': { code: '000001', name: '甲公司', skill_version: '4.4.0', dimensions: { business: 4, moat: 4, industry: 3, management: 3, financial: 5 }, weighted_score: 3.7, stars: 3, boundary: null, summary: '摘要', risks: [], watch_points: [], report_md: '正文', scored_at: '2026-11-01 10:00', data_date: '2026-10-30', analysis_duration_seconds: 12 },
      } } });
      return;
    }
    await route.fulfill({ status: 500, json: { detail: '阅读页不应请求其它接口' } });
  });
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  await page.waitForTimeout(1200);
  expect(paths.filter(path => path.includes('/refresh/jobs'))).toEqual([]);
  expect(paths.filter(path => path.includes('/quality') && path.startsWith('GET'))).toHaveLength(1);
});

test('a very long company name does not overflow the page', async ({ page }) => {
  const longName = '中国某某某某某某某某某某某某股份有限公司';
  const state = newState({
    scores: {
      '000001': score({ code: '000001', name: longName }),
      '000002': score({ code: '000002', name: '乙公司' }),
    },
  });
  await setupQualityApi(page, state);
  for (const viewport of [{ width: 360, height: 800 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport);
    await page.goto('/quality-reader?code=000001');
    await expect(page.getByRole('heading', { name: longName, exact: true })).toBeVisible();
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
  }
});

test('keyboard can reach and operate the reader controls', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await page.goto('/quality-reader?code=000001');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  // 控件有可读名称
  await expect(page.getByRole('button', { name: '刷新资料' })).toBeVisible();
  await expect(page.getByRole('button', { name: '上一篇', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '下一篇', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '← 返回股息率' })).toBeVisible();
  // 键盘触发下一篇
  await page.getByRole('button', { name: '下一篇', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/code=000002/);
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
});

/* ===== 主页面入口 ===== */

/** 主页面所需的最小 API mock：列表接口保持 pending 以便观察骨架屏 */
async function setupMainPage(page: Page, options: { stocksPending?: boolean } = {}) {
  const calls: string[] = [];
  await page.route('**/api/dividend/**', async route => {
    const url = new URL(route.request().url());
    calls.push(`${route.request().method()} ${url.pathname}`);
    if (url.pathname.endsWith('/stocks/screen')) {
      await route.fulfill({ json: {
        conditions: { min_yield: 3.5, min_roe: 10, min_roe_avg_3y: 10, max_quarter_profit_decline_pct: 30 },
        items: [], counts: { eligible: 0, excluded: 0, insufficient_data: 0 },
        dividend_years: [2023, 2024, 2025], total: 0, last_updated: null,
      } });
      return;
    }
    if (url.pathname.endsWith('/stocks')) {
      if (options.stocksPending) {
        await new Promise<void>(resolve => setTimeout(resolve, 30_000));
        await route.abort();
        return;
      }
      await route.fulfill({ json: { items: [], total: 0 } });
      return;
    }
    if (url.pathname.endsWith('/stats')) { await route.fulfill({ json: { total_stocks: 0 } }); return; }
    if (url.pathname.endsWith('/quality')) {
      await route.fulfill({ json: { total: 0, hermes_configured: true, current_skill_version: null, scores: {} } });
      return;
    }
    await route.fulfill({ json: { items: [], total: 0, needs_update: false, missing_codes: [], days_since_update: 0, enabled: false, levels: [] } });
  });
  return calls;
}

test('main page shows the reader entry in the 选股关注 view', async ({ page }) => {
  await setupMainPage(page);
  await page.goto('/?tab=screening');
  const entry = page.getByTestId('quality-reader-entry');
  await expect(entry).toBeVisible();
  await expect(entry).toHaveText('基本面资料阅读');
});

for (const view of [
  { path: '/', label: '全部' },
  { path: '/?tab=alerts', label: '挡位监控' },
]) {
  test(`main page has no reader entry in the ${view.label} view`, async ({ page }) => {
    await setupMainPage(page);
    await page.goto(view.path);
    await expect(page.getByTestId('quality-reader-entry')).toHaveCount(0);
  });
}

test('main page has no reader entry while the stock table is still loading', async ({ page }) => {
  await setupMainPage(page, { stocksPending: true });
  await page.goto('/');
  await expect(page.getByTestId('quality-reader-entry')).toHaveCount(0);
});

test('reader entry keeps the source view for the return link', async ({ page }) => {
  await setupMainPage(page);
  await page.goto('/?tab=screening');
  await expect(page.getByTestId('quality-reader-entry')).toHaveAttribute('href', /fromTab=screening/);
});

test('clicking the reader entry opens the independent reader page', async ({ page }) => {
  await setupMainPage(page);
  await page.goto('/?tab=screening');
  // 等待骨架屏切换为正式头部（骨架屏与正式头部是不同分支，切换会替换入口节点）
  await expect(page.getByRole('heading', { name: '股息率' })).toBeVisible();
  await page.getByTestId('quality-reader-entry').click();
  await expect(page).toHaveURL(/quality-reader/);
  await expect(page.getByRole('heading', { name: '基本面资料阅读' })).toBeVisible();
});

/* ===== 线上 /dividend 前缀兼容 ===== */

/**
 * 模拟 nginx 的剥前缀转发：浏览器地址带 /dividend，
 * 上游 Next 实际收到去掉前缀后的路径（与 nginx/web.conf 的 location /dividend/ 一致）。
 */
async function setupDividendPrefix(page: Page) {
  // 只拦截路径首段就是 /dividend 的请求（不能用 **/dividend/**，那会误伤 /api/dividend/*）
  await page.route(/^https?:\/\/[^/]+\/dividend\//, async route => {
    const url = new URL(route.request().url());
    const target = new URL(url.toString());
    target.pathname = url.pathname.replace(/^\/dividend/, '') || '/';
    try {
      const response = await route.fetch({ url: target.toString() });
      await route.fulfill({ response });
    } catch {
      // 测试收尾时可能有在途请求（页面已关闭），忽略即可
      await route.abort().catch(() => {});
    }
  });
}

test('online /dividend prefix keeps the prefix in the address bar across navigation', async ({ page }) => {
  const state = newState();
  await setupQualityApi(page, state);
  await setupDividendPrefix(page);
  await page.goto('/dividend/quality-reader?code=000001');
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '下一篇', exact: true }).click();
  await expect(page).toHaveURL(/\/dividend\/quality-reader\?code=000002/);
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  // 返回链接也保留线上前缀
  await expect(page.getByRole('link', { name: '← 返回股息率' })).toHaveAttribute('href', /^\/dividend\//);
  // 刷新后仍保留前缀与当前公司
  await page.reload();
  await expect(page.getByRole('heading', { name: '乙公司', exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/dividend\/quality-reader\?code=000002/);
  // 浏览器前进后退也在带前缀的地址间还原
  await page.goBack();
  await expect(page.getByRole('heading', { name: '甲公司', exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/dividend\/quality-reader\?code=000001/);
});
