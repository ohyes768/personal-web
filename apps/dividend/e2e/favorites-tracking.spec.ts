/**
 * 收藏跟踪（收藏跟踪 Tab，旧 ?tab=alerts URL）e2e
 *
 * 覆盖 AC1–AC6 的浏览器路径：收藏全集与筛选计数、待应用重叠语义、
 * 生效/候选/隐藏三种价格条、现价越界与缺失、首次评估到确认应用（应用前不开启监控）、
 * 暂停/恢复、非 ready 不可应用、失败重试与旧 URL 兼容。
 */
import { expect, test, type Page } from '@playwright/test';

const stockBase = {
  exchange: '深市主板', sw_level1: '银行', avg_yield_3y: 4.2,
  dividend_2025: 0.5,
};

type ReportStatus = 'ready' | 'insufficient_data' | 'blocked' | 'not_applicable';

export interface TrackingScenario {
  codes: string[];
  alerts: Record<string, { enabled: boolean; updated_at: string; levels: Record<string, { price: number; pe?: number; pb?: number }> } | undefined>;
  prices: Record<string, { close: number | null; realtime: number | null; pe: number | null; pb: number | null; yield_ttm: number | null } | undefined>;
  reports: Record<string, Record<string, unknown> | undefined>;
  perCode: Record<string, Record<string, unknown>>;
  analyzeCalls: string[][];
  applyCalls: Array<{ code: string; evaluated_at: string }>;
  enabledCalls: Array<{ code: string; enabled: boolean }>;
  applyStatus: number;
}

export function scenario(): TrackingScenario {
  return {
    codes: ['000001', '600000', '600004', '600005'],
    alerts: {
      // 000001：监控中（旧挡位四档，生效条可画）
      '000001': { enabled: true, updated_at: '2026-11-01T10:00:00', levels: {
        heavy_position: { price: 8.5, pe: 5.1, pb: 0.7 }, add_position: { price: 9.5, pe: 5.7, pb: 0.8 },
        reduce_position: { price: 14, pe: 8.4, pb: 1.0 }, full_exit: { price: 21, pe: 12.6, pb: 1.5 } } },
      // 600000：已暂停（手工只配一档 → 不画条，单挡位文本）
      '600000': { enabled: false, updated_at: '2026-11-02T10:00:00', levels: { heavy_position: { price: 9 } } },
      // 600004/600005：无挡位
      '600004': undefined,
      '600005': undefined,
    },
    prices: {
      '000001': { close: 11.9, realtime: 12.1, pe: 8.0, pb: 1.0, yield_ttm: 4.1 },
      '600000': { close: 10.0, realtime: 10.2, pe: 7.0, pb: 0.9, yield_ttm: 4.5 },
      '600004': { close: 27.8, realtime: 27.8, pe: 9.0, pb: 1.2, yield_ttm: 3.8 },
      '600005': undefined,
    },
    reports: {
      // 000001：重评 ready，evaluated_at 晚于 alerts.updated_at → 待应用重叠
      '000001': report('000001', '测试公司', 'ready', { evaluated_at: '2026-11-11T10:00:00' }),
      // 600000：非 ready（资料不足）→ 不出价格
      '600000': report('600000', '暂停公司', 'insufficient_data', { evaluated_at: '2026-11-10T10:00:00' }),
      // 600005：非 ready 且无旧挡位 → 占位说明 + 查看缺口
      '600005': report('600005', '缺口公司', 'insufficient_data', { evaluated_at: '2026-11-09T10:00:00' }),
      // 600004：无报告
      '600004': undefined,
    },
    perCode: {},
    analyzeCalls: [],
    applyCalls: [],
    enabledCalls: [],
    applyStatus: 0,
  };
}

function report(code: string, name: string, status: ReportStatus, opts?: { evaluated_at?: string; skill_version?: string | null }) {
  const levels = status === 'ready' ? {
    heavy_position: { price: 10, pe: 5.1, pb: 0.7 },
    add_position: { price: 12, pe: 6.1, pb: 0.8 },
    reduce_position: { price: 15, pe: 7.6, pb: 1.0 },
    full_exit: { price: 19, pe: 9.7, pb: 1.3 },
  } : null;
  return {
    schema_version: '1.0.0', skill_version: opts?.skill_version ?? '1.0.0',
    code, name, currency: 'CNY', as_of: '2026-11-11', status,
    levels, valuation: status === 'ready' ? { primary_method: 'pe_multiple' } : null,
    evidence: [{ id: 'e1', title: '年报摘要', kind: 'official', origin: 'inline:2026-11-11:年报',
      locator: '第二节', period: '2025 年度', published_at: '2026-03-30', accessed_at: '2026-11-11', verification: 'reused' }],
    data_gaps: status === 'insufficient_data' ? ['缺少可持续分红依据'] : [],
    confidence: { level: 'medium', reason: '上游复用' },
    risks: ['分红波动'], invalidation_conditions: ['分红政策变更'],
    summary: status === 'ready' ? '四点均有公司级依据' : '核心材料不足，暂不出价',
    analysis: { business: 'b', normalization: 'n', dividend: 'd', valuation: 'v', risk: 'r' },
    report_md: '## 估值依据\n\n内容完整。',
    evaluated_at: opts?.evaluated_at ?? '2026-11-11T10:00:00',
    data_date: '2026-10-12', analysis_duration_seconds: 92.5,
  };
}

export async function setup(page: Page, s: TrackingScenario) {
  await page.route('**/api/dividend/**', async route => {
    const url = new URL(route.request().url());
    const favorites = () => ({
      version: 1, total: s.codes.length, codes: s.codes,
      items: s.codes.map(code => ({
        code, added_at: '2026-10-09',
        alerts: s.alerts[code] ? { ...s.alerts[code] } : undefined,
      })),
      notify: { enabled: false, rules: [], last_notified_at: null },
    });
    const alertStatus = () => ({
      total: s.codes.length,
      enabled_count: s.codes.filter(code => s.alerts[code]?.enabled).length,
      triggered_today_count: 0,
      dingtalk_configured: false,
      items: s.codes.map(code => {
        const alerts = s.alerts[code];
        return {
          code, name: code === '000001' ? '测试公司' : code === '600000' ? '暂停公司' : code === '600005' ? '缺口公司' : '待评公司',
          enabled: !!alerts?.enabled,
          has_levels: !!alerts?.levels && Object.keys(alerts.levels).length > 0,
          level_count: alerts?.levels ? Object.keys(alerts.levels).length : 0,
          updated_at: alerts?.updated_at ?? null,
          levels: alerts?.levels ?? null,
          triggered_today: [],
        };
      }),
    });
    if (url.pathname.endsWith('/favorites/alerts/status')) {
      await route.fulfill({ json: alertStatus() });
    } else if (url.pathname.endsWith('/alerts/enabled')) {
      const code = url.pathname.split('/favorites/')[1].split('/')[0];
      const enabled = route.request().postDataJSON().enabled as boolean;
      s.enabledCalls.push({ code, enabled });
      const alerts = s.alerts[code];
      if (alerts) s.alerts[code] = { ...alerts, enabled };
      await route.fulfill({ json: favorites() });
    } else if (url.pathname.endsWith('/favorites')) {
      await route.fulfill({ json: favorites() });
    } else if (url.pathname.endsWith('/stocks')) {
      const requested = (url.searchParams.get('codes') ?? '').split(',').filter(Boolean);
      const names: Record<string, string> = { '000001': '测试公司', '600000': '暂停公司', '600004': '待评公司', '600005': '缺口公司' };
      await route.fulfill({ json: {
        total: requested.length,
        items: requested.map(code => ({ ...stockBase, code, name: names[code] ?? `股票${code}` })),
        last_updated: '2026-11-11',
      } });
    } else if (url.pathname.endsWith('/prices')) {
      const requested = (url.searchParams.get('codes') ?? '').split(',').filter(Boolean);
      await route.fulfill({ json: {
        total: requested.length,
        items: requested.map(code => ({ code, ...(s.prices[code] ?? {}) })),
        last_updated: '2026-11-11T15:00:00',
      } });
    } else if (url.pathname.endsWith('/valuation')) {
      await route.fulfill({ json: {
        total: Object.keys(s.reports).filter(code => s.reports[code]).length,
        reports: Object.fromEntries(Object.entries(s.reports).filter(([, v]) => !!v)),
        per_code: s.perCode,
        hermes_configured: true,
        current_skill_version: '1.0.0',
      } });
    } else if (url.pathname.endsWith('/valuation/analyze')) {
      const codes = route.request().postDataJSON().codes as string[];
      s.analyzeCalls.push(codes);
      for (const code of codes) s.perCode[code] = { state: 'running', error: null };
      await route.fulfill({ status: 202, json: {
        job_id: 'val-job-1', kind: 'valuation', status: 'running', total: codes.length,
        processed: 0, succeeded: 0, failed: 0, remaining: codes.length,
        codes, failed_codes: [], retry_codes: [], error: null, finished_at: null, message: '',
        per_code: s.perCode,
      } });
    } else if (url.pathname.includes('/valuation/jobs/')) {
      await route.fulfill({ json: {
        job_id: 'val-job-1', kind: 'valuation', status: 'succeeded', total: 1,
        processed: 1, succeeded: 1, failed: 0, remaining: 0,
        codes: [], failed_codes: [], retry_codes: [], error: null,
        finished_at: '2026-11-11T10:05:00', message: '已处理 1/1，成功 1，失败 0，未处理 0',
        per_code: s.perCode,
      } });
    } else if (url.pathname.endsWith('/apply')) {
      const code = url.pathname.split('/valuation/')[1].split('/')[0];
      const evaluated_at = route.request().postDataJSON().evaluated_at as string;
      s.applyCalls.push({ code, evaluated_at });
      if (s.applyStatus) {
        await route.fulfill({ status: s.applyStatus, json: { message: '报告已更新' } });
        return;
      }
      s.alerts[code] = { enabled: true, updated_at: '2026-11-11T11:00:00',
        levels: { heavy_position: { price: 10, pe: 5.1, pb: 0.7 }, add_position: { price: 12, pe: 6.1, pb: 0.8 },
          reduce_position: { price: 15, pe: 7.6, pb: 1.0 }, full_exit: { price: 19, pe: 9.7, pb: 1.3 } } };
      await route.fulfill({ json: favorites() });
    } else if (url.pathname.includes('/quality')) {
      await route.fulfill({ json: { total: 0, scores: {}, per_code: {}, hermes_configured: true, current_skill_version: '4.4.0' } });
    } else if (url.pathname.endsWith('/refresh/jobs')) {
      await route.fulfill({ json: null });
    } else if (url.pathname.endsWith('/stats')) {
      await route.fulfill({ json: { total_stocks: 100, yield_stats: {}, yield_distribution: {}, industry_distribution: {}, index_distribution: {}, csv_last_modified: null } });
    } else {
      await route.fulfill({ json: { needs_update: false, missing_codes: [], days_since_update: 0 } });
    }
  });
}

test('favorites tab shows all favorites with filter counts and legacy URL', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/?tab=alerts');
  await expect(page.getByText('4 只收藏 · 1 只监控中')).toBeVisible();
  // 三种筛选与计数（监控中/已暂停不设筛选：有挡位的默认都在列表里，行内徽章区分暂停）
  await expect(page.getByRole('button', { name: /全部收藏\s*4/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /待评估\s*2/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /待应用\s*1/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /监控中/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /已暂停/ })).toHaveCount(0);
  // 状态列已改名为「评估状态」（监控不再是这一列的事）
  await expect(page.getByRole('columnheader', { name: '评估状态' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '评估与监控状态' })).toHaveCount(0);
  // 四行都在
  const table = page.getByRole('table');
  await expect(table.getByText('测试公司')).toBeVisible();
  await expect(table.getByText('暂停公司')).toBeVisible();
  await expect(table.getByText('待评公司')).toBeVisible();
  await expect(table.getByText('缺口公司')).toBeVisible();
  // 非 ready 无旧挡位：占位说明 + 查看缺口，无应用按钮
  await expect(table.locator('[data-code="600005"]')).toContainText('核心材料不足，暂不出价');
  await expect(table.locator('[data-code="600005"]').getByRole('button', { name: '查看缺口' })).toBeVisible();
  await expect(table.locator('[data-code="600005"]').getByRole('button', { name: /应用/ })).toHaveCount(0);
  // 搜索过滤
  await page.getByLabel('搜索收藏的股票名称或代码').fill('600000');
  await expect(table.getByText('暂停公司')).toBeVisible();
  await expect(table.getByText('测试公司')).not.toBeVisible();
  await page.getByLabel('搜索收藏的股票名称或代码').fill('');
});

test('effective bar, single-level fallback and hidden bar follow state semantics', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  // 监控中行：生效条（无候选角标）
  const effective = table.locator('[data-code="000001"] [data-testid="valuation-bar-effective"]');
  await expect(effective).toBeVisible();
  // 精简后：每档 PE 与距各档距离走悬浮 tooltip，不再占条的高度
  await expect(effective).toHaveAttribute('title', /PE 5\.1/);
  await expect(effective).toHaveAttribute('title', /距/);
  // 区间名不在条里画了（图例是全局常量，每行重画既重复又被裁剪）
  await expect(effective).not.toContainText('持有区');
  // 结论落到独立的「区间」列：当前区 + 到下一个变盘线还有多远
  const zone = table.locator('[data-code="000001"] [data-testid="valuation-zone"]');
  await expect(zone).toContainText('持有区');
  // 现价 12.10，档位 8.5/9.5/14/21：↑减仓 (14-12.1)/12.1=15.7%，↓加仓 (12.1-9.5)/12.1=21.5%
  await expect(zone).toContainText('↑减仓 15.7%');
  await expect(zone).toContainText('↓加仓 21.5%');
  // 现价列只留价格与 PE/PB，距离不再混在这里
  await expect(table.locator('[data-code="000001"]')).not.toContainText('距减仓');
  // 重评待应用重叠：监控中 + 新评估待应用
  await expect(table.locator('[data-code="000001"]', { hasText: '新评估待应用' })).toBeVisible();
  await expect(table.locator('[data-code="000001"]').getByRole('button', { name: '应用' })).toBeVisible();
  await expect(table.locator('[data-code="000001"]').getByRole('button', { name: '查看报告' })).toBeVisible();
  // 已暂停 + 单挡位旧配置：条隐藏（不足两条价格线），显示单挡位文本
  await expect(table.locator('[data-code="600000"] [data-testid="valuation-bar-effective"]')).not.toBeVisible();
  await expect(table.locator('[data-code="600000"] [data-testid="valuation-bar-candidate"]')).not.toBeVisible();
  await expect(table.locator('[data-code="600000"]')).toContainText('单挡位 ¥9.00');
  // 待评估行：无条，占位文案
  await expect(table.locator('[data-code="600004"] [data-testid="valuation-bar-effective"]')).not.toBeVisible();
  await expect(table.locator('[data-code="600004"]').getByText('尚未评估，先评估挡位再决定是否开启监控')).toBeVisible();
});

test('first ready report shows candidate bar and applying enables monitoring', async ({ page }) => {
  const s = scenario();
  // 600004 生成首次 ready 报告（无旧挡位）
  s.reports['600004'] = report('600004', '待评公司', 'ready', { evaluated_at: '2026-11-11T09:00:00' });
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  // 候选条：价格弱化；「未启用」在条的悬浮说明里（条下不再有第三行）
  const candidate = table.locator('[data-code="600004"] [data-testid="valuation-bar-candidate"]');
  await expect(candidate).toBeVisible();
  await expect(candidate).toHaveAttribute('title', /未启用/);
  // 应用前：状态为待应用，不是监控中
  await expect(table.locator('[data-code="600004"]')).toContainText('待应用');
  // 「查看报告」与「应用」是两个独立动作：查看只开报告弹窗
  await table.locator('[data-code="600004"]').getByRole('button', { name: '查看报告' }).click();
  const reportDialog = page.getByRole('heading', { name: '待评公司 · 四挡位估值报告' }).locator('../..');
  await expect(reportDialog).toBeVisible();
  await expect(reportDialog.getByText('确认后保存四条价格线，并开启价格提醒。')).toBeVisible();
  await reportDialog.getByRole('button', { name: '暂不应用' }).click();
  await expect(reportDialog).not.toBeVisible();
  // 「应用」走紧凑确认卡，不打开报告弹窗
  await table.locator('[data-code="600004"]').getByRole('button', { name: '应用' }).click();
  const confirmDialog = page.getByRole('heading', { name: '确认应用挡位 · 待评公司' }).locator('../..');
  await expect(confirmDialog).toBeVisible();
  await expect(page.getByRole('heading', { name: '待评公司 · 四挡位估值报告' })).toHaveCount(0);
  await expect(confirmDialog.getByText('重仓')).toBeVisible();
  // 现价 ¥27.80 高于新全卖线 ¥19 → 应用后落在全卖区、会推「全部清仓」提醒
  await expect(confirmDialog.getByText('应用后落在 全卖区')).toBeVisible();
  await expect(confirmDialog.getByText(/会推送「全部清仓」钉钉提醒/)).toBeVisible();
  // 确认应用 → alerts 更新（enabled=true）
  await confirmDialog.getByTestId('valuation-confirm-apply-button').click();
  await expect(s.applyCalls).toEqual([{ code: '600004', evaluated_at: '2026-11-11T09:00:00' }]);
  await expect(confirmDialog).not.toBeVisible();
  // 应用后：生效条替换候选条；状态列讲评估（应用后不再是「待应用」）
  await expect(table.locator('[data-code="600004"] [data-testid="valuation-bar-effective"]')).toBeVisible();
  const applied = table.locator('[data-code="600004"]');
  await expect(applied.locator('[data-eval-state]')).toHaveAttribute('data-eval-state', 'succeeded');
  await expect(applied.locator('[data-eval-state]')).toContainText('评估完成');
  // 状态列不再混入监控（「监控中」只存在于挡位设置里）
  await expect(applied.locator('[data-eval-state]')).not.toContainText('监控');
});

test('stale apply is rejected with 409 and old monitoring stays untouched', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  s.applyStatus = 409;
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  await table.locator('[data-code="000001"]').getByRole('button', { name: '应用' }).click();
  const confirmDialog = page.getByRole('heading', { name: '确认应用挡位 · 测试公司' }).locator('../..');
  await expect(confirmDialog).toBeVisible();
  // 新旧对比：旧生效价一列可见
  await expect(confirmDialog.getByText('¥8.50')).toBeVisible();
  // 现价 ¥12.10 在新旧两套挡位里都落在持有区 → 不触发提醒
  await expect(confirmDialog.getByText(/旧挡位在 持有区（不触发提醒）/)).toBeVisible();
  await expect(confirmDialog.getByText('应用后不会触发提醒')).toBeVisible();
  await confirmDialog.getByTestId('valuation-confirm-apply-button').click();
  await expect(confirmDialog.getByRole('alert')).toContainText('报告已更新');
  // 旧挡位未被动过
  expect(s.alerts['000001']?.updated_at).toBe('2026-11-01T10:00:00');
});

test('non-ready report cannot be applied and failure retriable', async ({ page }) => {
  const s = scenario();
  s.perCode['600004'] = { state: 'failed', error: 'run 终态 failed' };
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  // 非 ready 行不出现「应用」按钮
  await expect(table.locator('[data-code="600000"]').getByRole('button', { name: /应用/ })).toHaveCount(0);
  // 失败行显示原因与重试
  await expect(table.locator('[data-code="600004"]')).toContainText('评估失败');
  await table.locator('[data-code="600004"]').getByRole('button', { name: '重试评估' }).click();
  await expect(s.analyzeCalls).toEqual([['600004']]);
});

test('failed valuation row offers the failed run session download', async ({ page }) => {
  const s = scenario();
  s.perCode['600004'] = { state: 'failed', error: 'run 终态 failed', run_id: 'run-val-fail-1' };
  await setup(page, s);
  await page.route('**/api/dividend/valuation/runs/run-val-fail-1/session', route => route.fulfill({
    status: 200,
    contentType: 'text/markdown; charset=utf-8',
    body: '# Hermes run 会话记录：run-val-fail-1\n\n## 消息记录（0 条）\n',
  }));
  await page.goto('/?tab=alerts');
  const row = page.getByRole('table').locator('[data-code="600004"]');
  await expect(row).toContainText('评估失败');
  const button = row.getByRole('button', { name: '下载会话记录' });
  await expect(button).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await button.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('hermes-run-val-fail-1-session.md');
});

test('succeeded valuation row also offers the session download', async ({ page }) => {
  const s = scenario();
  // 000001 有 ready 报告，让这次成功评估带上 run_id（会话记录挂在报告上）
  s.reports['000001'] = { ...s.reports['000001']!, run_id: 'run-val-ok-1' };
  await setup(page, s);
  await page.route('**/api/dividend/valuation/runs/run-val-ok-1/session', route => route.fulfill({
    status: 200,
    contentType: 'text/markdown; charset=utf-8',
    body: '# Hermes run 会话记录：run-val-ok-1\n\n## 消息记录（3 条）\n',
  }));
  await page.goto('/?tab=alerts');
  const row = page.getByRole('table').locator('[data-code="000001"]');
  await expect(row.locator('[data-eval-state]')).toBeVisible();
  const button = row.getByRole('button', { name: '下载会话记录' });
  await expect(button).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await button.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('hermes-run-val-ok-1-session.md');
});

test('paused rows keep the badge but the row no longer offers pause actions', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  const row = table.locator('[data-code="600000"]');
  // 状态列只讲评估：该行有非 ready 报告 → 未出价格；监控开关不再占据这一列
  await expect(row.locator('[data-eval-state]')).toHaveAttribute('data-eval-state', 'not_ready');
  await expect(row).not.toContainText('已暂停');
  // 行内不再有暂停/恢复入口（启用监控改到「挡位设置」里勾选）
  await expect(row.getByRole('button', { name: '暂停' })).toHaveCount(0);
  await expect(row.getByRole('button', { name: '恢复监控' })).toHaveCount(0);
  await expect(row.getByRole('button', { name: '挡位设置' })).toBeVisible();
  // 挡位条仍显示（保留配置）
  await expect(table.locator('[data-code="000001"] [data-testid="valuation-bar-effective"]')).toBeVisible();
});

test('out-of-range and missing current price are explicit, not misleading', async ({ page }) => {
  const s = scenario();
  s.prices['600004'] = { close: 27.8, realtime: 2.0, pe: 9.0, pb: 1.2, yield_ttm: 3.8 }; // 低于全部阈值
  s.reports['600004'] = report('600004', '待评公司', 'ready', { evaluated_at: '2026-11-11T09:00:00' });
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  // 低于全部阈值：区间仍是重仓区，但方向变成「↑重仓」——涨回去才离开重仓区
  const zone = table.locator('[data-code="600004"] [data-testid="valuation-zone"]');
  await expect(zone).toContainText('重仓区');
  await expect(zone).toContainText('↑重仓');
  // 缺现价（realtime 与 close 都缺失才视为缺失）
  s.prices['600000'] = { close: null, realtime: null, pe: null, pb: null, yield_ttm: null };
  await page.reload();
  await expect(table.locator('[data-code="600000"]').getByText('现价缺失')).toBeVisible();
});

test('narrow viewport keeps primary actions reachable without page overflow', async ({ page }) => {
  const s = scenario();
  s.reports['600004'] = report('600004', '待评公司', 'ready', { evaluated_at: '2026-11-11T09:00:00' });
  await setup(page, s);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  await expect(table.getByText('测试公司')).toBeVisible();
  // 页面整体不横向溢出（表格容器内部横滑是允许的）
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
  // 主操作可达：待应用的「应用」与「查看报告」、非 ready 行的缺口入口都在窄屏渲染
  await expect(table.locator('[data-code="600004"]').getByRole('button', { name: '应用' })).toBeVisible();
  await expect(table.locator('[data-code="600004"]').getByRole('button', { name: '查看报告' })).toBeVisible();
  await expect(table.locator('[data-code="600005"]').getByRole('button', { name: '查看缺口' })).toBeVisible();
  // 重新评估收在报告面板里（行内不再重复一个入口）
  await table.locator('[data-code="600005"]').getByRole('button', { name: '查看缺口' }).click();
  const gapDialog = page.getByRole('heading', { name: '缺口公司 · 四挡位估值报告' }).locator('../..');
  await expect(gapDialog.getByRole('button', { name: '重新评估' })).toBeVisible();
  await gapDialog.getByRole('button', { name: '返回列表' }).click();
});
