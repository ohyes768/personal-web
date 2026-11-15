/**
 * 收藏跟踪（收藏跟踪 Tab，旧 ?tab=alerts URL）e2e
 *
 * 覆盖 AC1–AC6 的浏览器路径：收藏全集与筛选计数、待应用重叠语义、
 * 生效/候选/隐藏三种价格条、现价越界与缺失、首次评估到确认应用（应用前不使用该挡位）、
 * 暂停/恢复、非 ready 不可应用、失败重试与旧 URL 兼容。
 */
import { expect, test } from '@playwright/test';
import { report, scenario, setup } from './tracking-fixture';

test('favorites tab shows all favorites with filter counts and legacy URL', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/?tab=alerts');
  await expect(page.getByText('4 只收藏 · 1 份待确认')).toBeVisible();
  // 三种筛选与计数（推送与监控已移除，不再有按启停状态的筛选）
  await expect(page.getByRole('button', { name: /全部收藏\s*4/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /待评估\s*2/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /待应用\s*1/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /监控中/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /已暂停/ })).toHaveCount(0);
  // 评估列已合并「状态 + 版本 + 会话下载」（原「评估状态」与「评估 / 版本」两列）
  await expect(page.getByRole('columnheader', { name: '评估' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '评估状态' })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: '评估 / 版本' })).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: '评估与监控状态' })).toHaveCount(0);
  // 四行都在
  const table = page.getByRole('table');
  await expect(table.getByText('测试公司')).toBeVisible();
  await expect(table.getByText('暂停公司')).toBeVisible();
  await expect(table.getByText('待评公司')).toBeVisible();
  await expect(table.getByText('缺口公司')).toBeVisible();
  // 非 ready 无旧挡位：占位说明 + 查看缺口链接，无应用按钮
  await expect(table.locator('[data-code="600005"]')).toContainText('核心材料不足，暂不出价');
  await expect(table.locator('[data-code="600005"]').getByRole('link', { name: /^查看缺口/ })).toBeVisible();
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
  // 已配置挡位行：生效条（无候选角标）
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
  // 重评待应用重叠：已有生效挡位 + 新评估待应用
  await expect(table.locator('[data-code="000001"]', { hasText: '新评估待应用' })).toBeVisible();
  await expect(table.locator('[data-code="000001"]').getByRole('button', { name: '应用' })).toBeVisible();
  // 「查看报告」是链接：跳独立阅读页，不再开弹窗
  await expect(table.locator('[data-code="000001"]').getByRole('link', { name: /^查看报告/ })).toBeVisible();
  // 生效条只画一条，候选那套价不进表格（由确认卡与阅读页承载）
  await expect(table.locator('[data-code="000001"] [data-testid="valuation-bar-effective"]')).toHaveCount(1);
  await expect(table.locator('[data-code="000001"] [data-testid="valuation-bar-candidate"]')).toHaveCount(0);
  // 生效挡位的时间标在条下（版本不写：报告按 code 覆盖后查不到生效那套的版本）
  await expect(table.locator('[data-code="000001"]')).toContainText('生效于 11-01 10:00');
  // 单挡位旧配置：条隐藏（不足两条价格线），显示单挡位文本
  await expect(table.locator('[data-code="600000"] [data-testid="valuation-bar-effective"]')).not.toBeVisible();
  await expect(table.locator('[data-code="600000"] [data-testid="valuation-bar-candidate"]')).not.toBeVisible();
  await expect(table.locator('[data-code="600000"]')).toContainText('单挡位 ¥9.00');
  // 待评估行：无条，占位文案
  await expect(table.locator('[data-code="600004"] [data-testid="valuation-bar-effective"]')).not.toBeVisible();
  await expect(table.locator('[data-code="600004"]').getByText('尚未评估，先评估挡位再决定是否设置')).toBeVisible();
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
  // 应用前：状态为待应用，尚未使用该挡位
  await expect(table.locator('[data-code="600004"]')).toContainText('待应用');
  // 「查看报告」与「应用」是两个独立动作：查看是链接，指向独立阅读页（不再开报告弹窗）
  const reportLink = table.locator('[data-code="600004"]').getByRole('link', { name: /^查看报告/ });
  await expect(reportLink).toHaveAttribute('href', '/valuation-reader?code=600004&fromTab=alerts');
  // 「应用」走紧凑确认卡
  await table.locator('[data-code="600004"]').getByRole('button', { name: '应用' }).click();
  const confirmDialog = page.getByRole('heading', { name: '确认应用挡位 · 待评公司' }).locator('../..');
  await expect(confirmDialog).toBeVisible();
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
  // 状态列不再混入监控（推送与监控已整体移除）
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
  // 行内没有暂停/恢复入口（该功能已移除）
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
  await expect(table.locator('[data-code="600004"]').getByRole('link', { name: /^查看报告/ })).toBeVisible();
  await expect(table.locator('[data-code="600005"]').getByRole('link', { name: /^查看缺口/ })).toBeVisible();
  // 重新评估是行内常驻入口（不再收在报告面板里）
  await expect(table.locator('[data-code="600005"]').getByRole('button', { name: '再评估' })).toBeVisible();
});

test('evaluated rows keep a re-evaluate entry, and it asks before overwriting a pending report', async ({ page }) => {
  const s = scenario();
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const table = page.getByRole('table');
  // 已评估过的行也要有评估入口：没评估过的叫「评估挡位」，评估过的叫「再评估」
  await expect(table.locator('[data-code="600004"]').getByRole('button', { name: '评估挡位' })).toBeVisible();
  await expect(table.locator('[data-code="000001"]').getByRole('button', { name: '再评估' })).toBeVisible();
  await expect(table.locator('[data-code="600005"]').getByRole('button', { name: '再评估' })).toBeVisible();
  // 没有待应用报告时直接提交，不打扰
  await table.locator('[data-code="600005"]').getByRole('button', { name: '再评估' }).click();
  await expect(s.analyzeCalls).toEqual([['600005']]);
  // 有待应用报告时先确认（覆盖的是尚未生效的报告）
  await table.locator('[data-code="000001"]').getByRole('button', { name: '再评估' }).click();
  const confirm = page.getByRole('heading', { name: '确认重新评估' }).locator('../..');
  await expect(confirm).toBeVisible();
  await expect(confirm).toContainText('会覆盖');
  await expect(s.analyzeCalls).toEqual([['600005']]);
  await confirm.getByRole('button', { name: '确认重新评估' }).click();
  await expect(s.analyzeCalls).toEqual([['600005'], ['000001']]);
});

test('a failed attempt does not hide the pending report: retry and apply both stay available', async ({ page }) => {
  const s = scenario();
  // 000001 有一份新的 ready 报告待应用，但最近一次尝试失败了
  s.perCode['000001'] = {
    state: 'failed', error: 'run 终态 failed', run_id: 'run-val-fail-2',
    finished_at: '2026-11-15T10:02:00',
  };
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const row = page.getByRole('table').locator('[data-code="000001"]');
  // 状态讲的是最近一次尝试：失败
  await expect(row.locator('[data-eval-state]')).toHaveAttribute('data-eval-state', 'failed');
  await expect(row).toContainText('评估失败');
  // 溯源行写的是本次失败的时间（不是旧报告的时间）
  await expect(row).toContainText('11-15 10:02');
  // 失败不盖住待应用：重试与应用同时给出
  await expect(row.getByRole('button', { name: '重试评估' })).toBeVisible();
  await expect(row.getByRole('button', { name: '应用' })).toBeVisible();
  // 会话下载指向失败那次
  await expect(row.getByRole('button', { name: '下载会话记录' })).toBeVisible();
});

test('the evaluation column keeps time, version and session download on the same attempt', async ({ page }) => {
  const s = scenario();
  // 000001 已应用（报告早于生效挡位），评估列写的是那份报告的时间与版本
  s.alerts['000001'] = {
    updated_at: '2026-11-12T10:00:00',
    levels: s.alerts['000001']!.levels,
  };
  await setup(page, s);
  await page.goto('/?tab=alerts');
  const row = page.getByRole('table').locator('[data-code="000001"]');
  // 已应用：徽章是评估完成，溯源写报告的时间与版本
  await expect(row.locator('[data-eval-state]')).toHaveAttribute('data-eval-state', 'succeeded');
  await expect(row).toContainText('11-11 10:00');
  await expect(row).toContainText('v1.0.0');
  // 生效条下面只标生效时间，不标生效那套的版本（报告按 code 覆盖后查不到）
  await expect(row).toContainText('生效于 11-12 10:00');
  await expect(row.locator('[data-testid="valuation-bar-effective"]')).toHaveCount(1);
  // 报告入口与状态徽章同列（评估列）：它和「下载会话记录」一样是这次评估的产物。
  // 操作列只留对股票的动作，不放链接。
  const evalCell = row.locator('td:has([data-eval-state])');
  await expect(evalCell.getByRole('link', { name: /^查看报告/ })).toBeVisible();
  await expect(row.locator('td').last().getByRole('link')).toHaveCount(0);
});
