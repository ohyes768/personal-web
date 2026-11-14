/**
 * ScreeningCheckPanel — 基本面资料阅读页的「筛选条件复核」面板
 *
 * 逐条列出当前公司按当前筛选条件的判定（符合 / 不符 / 待补 / 提示），
 * 不符与待补的行直接标出来，阅读报告时一眼能看到哪些指标需要复核。
 * 判定与「选股关注」页同源（后端 screening_service.build_checks），这里只做展示。
 */
'use client';

import {
  SCREENING_CHECK_LABELS,
  isDefaultScreeningConditions,
  summarizeChecks,
  type ScreeningCheckResult,
  type ScreeningConditions,
  type StockScreeningResponse,
} from '@/lib/screening';

const RESULT_STYLES: Record<ScreeningCheckResult, string> = {
  pass: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  fail: 'border-red-200 bg-red-50 text-red-700',
  missing: 'border-rule-strong bg-paper-deep text-ink-muted',
  warn: 'border-amber-200 bg-amber-50 text-amber-700',
};

const ROW_STYLES: Record<ScreeningCheckResult, string> = {
  pass: '',
  fail: 'bg-red-50/70',
  missing: '',
  warn: '',
};

const STATUS_LABELS: Record<StockScreeningResponse['status'], string> = {
  eligible: '符合条件',
  excluded: '未符合',
  insufficient_data: '待补数据',
};

const STATUS_STYLES: Record<StockScreeningResponse['status'], string> = {
  eligible: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  excluded: 'border-red-200 bg-red-50 text-red-700',
  insufficient_data: 'border-rule-strong bg-paper-deep text-ink-muted',
};

/** 当前筛选条件的口径说明（与选股关注页同一套阈值） */
function conditionsText(conditions: ScreeningConditions): string {
  return [
    `近三年平均股息率 ≥${conditions.min_yield}%`,
    `最近年度 ROE ≥${conditions.min_roe}%`,
    `近三年平均 ROE ≥${conditions.min_roe_avg_3y}%`,
    `单季扣非最大降幅 ${conditions.max_quarter_profit_decline_pct}%`,
    `扣非 3 年 CAGR ≥${conditions.min_cagr_3y}%`,
  ].join(' · ');
}

export interface ScreeningCheckPanelProps {
  data: StockScreeningResponse | null;
  loading: boolean;
  error: string | null;
}

export function ScreeningCheckPanel({ data, loading, error }: ScreeningCheckPanelProps) {
  if (loading && !data) {
    return (
      <section className="quality-reader-check" aria-label="筛选条件复核">
        <h2 className="quality-reader-section">筛选条件复核</h2>
        <p className="quality-reader-text text-ink-muted" role="status">正在按当前筛选条件核对…</p>
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="quality-reader-check" aria-label="筛选条件复核">
        <h2 className="quality-reader-section">筛选条件复核</h2>
        <p className="quality-reader-text text-amber-700" role="alert">筛选复核加载失败：{error}</p>
      </section>
    );
  }

  if (!data || !Array.isArray(data.checks)) return null;

  const summary = summarizeChecks(data.checks);
  const reasons = Array.isArray(data.reasons) ? data.reasons : [];
  const warnings = Array.isArray(data.warnings) ? data.warnings : [];
  const notes: string[] = [];
  if (summary.fail > 0) notes.push(`${summary.fail} 项不符合，需复核`);
  if (summary.missing > 0) notes.push(`${summary.missing} 项数据待补`);
  if (summary.warn > 0) notes.push(`${summary.warn} 项提示`);
  const summaryText = notes.length > 0 ? notes.join(' · ') : '全部条件符合当前筛选条件';

  return (
    <section className="quality-reader-check" aria-label="筛选条件复核">
      <h2 className="quality-reader-section">筛选条件复核</h2>

      <div className="quality-reader-check-head">
        <span className={`quality-reader-check-status ${STATUS_STYLES[data.status]}`}>{STATUS_LABELS[data.status]}</span>
        <span className="quality-reader-text">{summaryText}</span>
      </div>
      <p className="quality-reader-text text-xs text-ink-muted">
        条件：{conditionsText(data.conditions)}
        {isDefaultScreeningConditions(data.conditions) ? '（默认条件）' : '（选股关注页保存的条件）'}
        {data.financial_last_updated && ` · 财务数据 ${data.financial_last_updated.slice(0, 10)}`}
        {data.last_updated && ` · 分红数据 ${data.last_updated.slice(0, 10)}`}
      </p>

      <div className="quality-reader-table-wrap rounded-lg border border-rule">
        <table className="quality-reader-text w-full">
          <thead className="bg-paper-deep text-left">
            <tr>
              <th className="p-2 font-medium">条件</th>
              <th className="p-2 font-medium">门槛</th>
              <th className="p-2 font-medium">当前值</th>
              <th className="p-2 font-medium">结论</th>
            </tr>
          </thead>
          <tbody>
            {data.checks.map(check => (
              <tr key={check.key} className={`border-t border-rule ${ROW_STYLES[check.result]}`}>
                <td className="p-2">
                  {check.label}
                  {check.detail && <span className="block text-xs text-ink-muted">{check.detail}</span>}
                </td>
                <td className="p-2 whitespace-nowrap font-mono tabular-nums">{check.threshold_text}</td>
                <td className="p-2 whitespace-nowrap font-mono tabular-nums">{check.value_text}</td>
                <td className="p-2">
                  <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${RESULT_STYLES[check.result]}`}>
                    {check.result === 'fail' ? '不符 · 需复核' : SCREENING_CHECK_LABELS[check.result]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {reasons.length > 0 && (
        <div className="quality-reader-check-notes">
          <h3 className="quality-reader-text font-medium text-red-700">未符合原因</h3>
          <ul className="quality-reader-list">
            {reasons.map(reason => <li key={reason}>{reason}</li>)}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="quality-reader-check-notes">
          <h3 className="quality-reader-text font-medium text-amber-700">提示</h3>
          <ul className="quality-reader-list">
            {warnings.map(warning => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      )}

      <p className="text-xs text-ink-soft">判定口径与「选股关注」页一致；不符与待补的条目是阅读报告时优先复核的地方。</p>
    </section>
  );
}
