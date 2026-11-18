/**
 * 收藏跟踪 / 估值阅读页共用的 e2e mock 场景
 *
 * 单独成文件而不是挂在某个 .spec.ts 里：Playwright 会把 import 到的 spec 文件
 * 也当测试文件收集，共享代码放这里才不会连带跑起另一套用例。
 */
import type { Page } from '@playwright/test';

const stockBase = {
  exchange: '深市主板', sw_level1: '银行', avg_yield_3y: 4.2,
  dividend_2025: 0.5,
};

type ReportStatus = 'ready' | 'insufficient_data' | 'blocked' | 'not_applicable';

export interface TrackingScenario {
  codes: string[];
  alerts: Record<string, { updated_at: string; levels: Record<string, { price: number; pe?: number; pb?: number }> } | undefined>;
  prices: Record<string, { close: number | null; realtime: number | null; pe: number | null; pb: number | null; yield_ttm: number | null } | undefined>;
  reports: Record<string, Record<string, unknown> | undefined>;
  perCode: Record<string, Record<string, unknown>>;
  analyzeCalls: string[][];
  applyCalls: Array<{ code: string; evaluated_at: string }>;
  applyStatus: number;
}

export function scenario(): TrackingScenario {
  return {
    codes: ['000001', '600000', '600004', '600005'],
    alerts: {
      // 000001：已配置四档（生效条可画）
      '000001': { updated_at: '2026-11-01T10:00:00', levels: {
        heavy_position: { price: 8.5, pe: 5.1, pb: 0.7 }, add_position: { price: 9.5, pe: 5.7, pb: 0.8 },
        reduce_position: { price: 14, pe: 8.4, pb: 1.0 }, full_exit: { price: 21, pe: 12.6, pb: 1.5 } } },
      // 600000：手工只配一档（不画条，显示单挡位文本）
      '600000': { updated_at: '2026-11-02T10:00:00', levels: { heavy_position: { price: 9 } } },
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
    applyStatus: 0,
  };
}

export function report(code: string, name: string, status: ReportStatus, opts?: { evaluated_at?: string; skill_version?: string | null }) {
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
      items: s.codes.map(code => {
        const alerts = s.alerts[code];
        return {
          code, name: code === '000001' ? '测试公司' : code === '600000' ? '暂停公司' : code === '600005' ? '缺口公司' : '待评公司',
          has_levels: !!alerts?.levels && Object.keys(alerts.levels).length > 0,
          level_count: alerts?.levels ? Object.keys(alerts.levels).length : 0,
          updated_at: alerts?.updated_at ?? null,
          levels: alerts?.levels ?? null,
        };
      }),
    });
    if (url.pathname.endsWith('/favorites/alerts/status')) {
      await route.fulfill({ json: alertStatus() });
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
      s.alerts[code] = { updated_at: '2026-11-11T11:00:00',
        levels: { heavy_position: { price: 10, pe: 5.1, pb: 0.7 }, add_position: { price: 12, pe: 6.1, pb: 0.8 },
          reduce_position: { price: 15, pe: 7.6, pb: 1.0 }, full_exit: { price: 19, pe: 9.7, pb: 1.3 } } };
      await route.fulfill({ json: favorites() });
    } else if (url.pathname.includes('/quality')) {
      await route.fulfill({ json: { total: 0, scores: {}, per_code: {}, hermes_configured: true, current_skill_version: '4.4.0' } });
    } else if (url.pathname.endsWith('/refresh/jobs')) {
      await route.fulfill({ json: null });
    } else if (url.pathname.endsWith('/stats')) {
      await route.fulfill({ json: { total_stocks: 100, yield_stats: {}, yield_distribution: {}, industry_distribution: {}, csv_last_modified: null } });
    } else {
      await route.fulfill({ json: { needs_update: false, missing_codes: [], days_since_update: 0 } });
    }
  });
}
