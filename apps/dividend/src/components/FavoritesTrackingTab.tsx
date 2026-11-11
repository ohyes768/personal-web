/**
 * FavoritesTrackingTab — 收藏跟踪（替换原「挡位监控」Tab，?tab=alerts URL 保持兼容）
 *
 * 展示全部收藏（不限于已配置挡位），五种筛选 + 名称/代码搜索：
 *   全部收藏 / 待评估（从未应用挡位且无待应用报告）/ 待应用（可与监控中/已暂停重叠）
 *   / 监控中 / 已暂停
 * 行内：评估挡位/重评/重试、查看报告、对比并应用（ready 报告确认后才写 alerts 并开启监控）、
 *   暂停/恢复监控、挡位设置（既有 AlertSettingsModal）。
 * 价格条：ValuationPriceBar 窄条（四阈值五区间）；未评估/失败/非 ready 不画条。
 */
'use client';

import { useCallback, useMemo, useState } from 'react';
import { dividendApi } from '@/lib/api';
import { useQualityAnalysis } from '@/lib/hooks/useQualityAnalysis';
import { useValuation } from '@/lib/hooks/useValuation';
import { QUALITY_DIMENSION_LABELS, QUALITY_DIMENSION_ORDER, type QualityDimensionKey } from '@/lib/quality';
import {
  TRACKING_STATE_META,
  VALUATION_LEVEL_KEYS,
  VALUATION_STATUS_LABEL,
  deriveFavoriteTrackingState,
  matchesTrackingFilter,
  reportLevelsToAlertLevels,
  type FavoriteTrackingDerived,
  type TrackingFilterKey,
  type ValuationReportRecord,
} from '@/lib/valuation';
import type { AlertLevels, DividendStockWithTechnical, PriceItem } from '@/lib/types';
import type { UseAlertsStatusResult } from '@/lib/hooks/useAlertsStatus';
import type { UseWatchlistResult } from '@/lib/hooks/useWatchlist';
import { ValuationPriceBar } from './ValuationPriceBar';
import { ValuationReportModal } from './ValuationReportModal';

const FILTERS: Array<{ key: TrackingFilterKey; label: string }> = [
  { key: 'all', label: '全部收藏' },
  { key: 'pending', label: '待评估' },
  { key: 'ready', label: '待应用' },
  { key: 'monitoring', label: '监控中' },
  { key: 'paused', label: '已暂停' },
];

const chip = 'rounded border px-2.5 py-1 text-xs transition-colors';
const chipActive = 'bg-paper-deep border-accent text-accent font-medium';
const chipIdle = 'border-rule text-ink-muted hover:text-ink hover:border-rule-strong';
const linkBtn = 'text-xs text-accent hover:underline underline-offset-4 disabled:opacity-40 disabled:no-underline';
const ghostBtn = 'rounded border border-rule-strong px-2.5 py-1 text-xs text-ink hover:bg-paper-tint disabled:opacity-40';
const primaryBtn = 'rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50';

function normalize(keyword: string): string {
  return keyword.trim().toLowerCase();
}

export function FavoritesTrackingTab({
  watchlist,
  stocks,
  alertsStatus,
  priceMap,
  priceUpdatedAt,
  onOpenAlertSettings,
}: {
  watchlist: UseWatchlistResult;
  stocks: DividendStockWithTechnical[];
  alertsStatus: UseAlertsStatusResult;
  /** 现价（page 级 useRealtimePrices 统一拉取，避免与本组件重复请求） */
  priceMap: Map<string, PriceItem>;
  priceUpdatedAt: string | null;
  onOpenAlertSettings: (code: string) => void;
}) {
  const [filter, setFilter] = useState<TrackingFilterKey>('all');
  const [searchInput, setSearchInput] = useState('');
  const [reportCode, setReportCode] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [applyError, setApplyError] = useState('');

  const { reports, perCode, configured, currentSkillVersion, job, message: valuationMessage, pollError, analyze, refresh: refreshValuation } = useValuation();
  const { qualityScores, currentSkillVersion: qualityVersion } = useQualityAnalysis();
  const keyword = normalize(searchInput);
  const stockByCode = useMemo(() => {
    const map = new Map<string, DividendStockWithTechnical>();
    stocks.forEach(s => map.set(s.code, s));
    return map;
  }, [stocks]);
  const codes = useMemo(() => [...watchlist.codes], [watchlist.codes]);

  const rows = useMemo(() => {
    return codes.map(code => {
      const stock = stockByCode.get(code) || { code, name: '资料待补', exchange: '' } as DividendStockWithTechnical;
      const alertItem = alertsStatus.alertMap.get(code);
      const report = reports[code] ?? null;
      const live = perCode[code] ?? null;
      const derived = deriveFavoriteTrackingState(
        alertItem?.enabled,
        alertItem?.levels ?? null,
        alertItem?.updated_at ?? null,
        report,
        live,
      );
      const price = priceMap.get(code);
      const currentPrice = price?.realtime ?? price?.close ?? null;
      return { code, stock, alertItem, report, derived, currentPrice, price, liveError: live?.error ?? null };
    });
  }, [codes, stockByCode, alertsStatus.alertMap, reports, perCode, priceMap]);

  const visible = useMemo(() => {
    return rows.filter(row => {
      if (!matchesTrackingFilter(filter, row.derived)) return false;
      if (!keyword) return true;
      return row.stock.name.toLowerCase().includes(keyword) || row.code.includes(keyword);
    });
  }, [rows, filter, keyword]);

  const counts = useMemo(() => {
    const result = {} as Record<TrackingFilterKey, number>;
    FILTERS.forEach(({ key }) => {
      result[key] = rows.filter(row => matchesTrackingFilter(key, row.derived)).length;
    });
    return result;
  }, [rows]);

  const pendingApplyCount = counts.ready;
  const monitoringCount = counts.monitoring;

  const submitEvaluate = useCallback(async (codeList: string[]) => {
    if (!codeList.length) return;
    setActionPending(codeList.join(','));
    await analyze(codeList);
    setActionPending(null);
  }, [analyze]);

  const handleApply = useCallback(async (report: ValuationReportRecord) => {
    setApplyError('');
    setActionPending(report.code);
    try {
      await dividendApi.applyValuationReport(report.code, report.evaluated_at);
      await Promise.all([alertsStatus.refresh(), refreshValuation()]);
      setNotice(`${report.name} 挡位已应用，监控已开启`);
      setReportCode(null);
    } catch (err) {
      const text = err instanceof Error ? err.message : '应用失败，请重试';
      setApplyError(text);
    } finally {
      setActionPending(null);
    }
  }, [alertsStatus, refreshValuation]);

  const handleToggleEnabled = useCallback(async (code: string, enabled: boolean) => {
    setActionPending(code);
    try {
      await dividendApi.setAlertsEnabled(code, enabled);
      await alertsStatus.refresh();
      setNotice(enabled ? '已恢复监控，挡位配置保留' : '已暂停提醒，挡位配置保留');
    } catch (err) {
      setNotice(err instanceof Error ? `操作失败：${err.message}` : '操作失败，请重试');
    } finally {
      setActionPending(null);
    }
  }, [alertsStatus]);

  const openReport = useCallback((code: string) => {
    setApplyError('');
    setReportCode(code);
  }, []);

  const reportModalCode = reportCode;
  const reportModalRecord = reportModalCode ? reports[reportModalCode] ?? null : null;
  const reportModalEffective: AlertLevels | null = reportModalCode
    ? (alertsStatus.alertMap.get(reportModalCode)?.levels ?? null)
    : null;
  const jobProgress = job && (job.status === 'queued' || job.status === 'running')
    ? { processed: job.processed, total: job.total }
    : null;

  return (
    <section aria-label="收藏跟踪" className="space-y-3">
      {/* 顶部：说明 + 汇总 */}
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-ink">收藏跟踪</h2>
          <p className="text-sm text-ink-muted">好公司先收藏，评估确认后价格才有尺度。收藏不自动评估，也不自动开启监控。</p>
        </div>
        <p className="text-xs text-ink-muted">
          {rows.length} 只收藏 · {monitoringCount} 只监控中
          {pendingApplyCount > 0 && <span className="text-accent font-medium"> · {pendingApplyCount} 份待确认</span>}
        </p>
      </div>

      {/* 待应用提示条 */}
      {pendingApplyCount > 0 && (
        <div className="rounded-lg border border-rule bg-paper-tint px-4 py-2.5 flex items-center justify-between gap-3">
          <p className="text-sm text-ink">
            <b>{pendingApplyCount} 份挡位评估等待确认</b>
            <span className="text-ink-muted"> · 包含首次评估与监控中的新评估，应用前旧挡位持续生效</span>
          </p>
          <button type="button" className={`${chip} ${chipActive} shrink-0`} onClick={() => setFilter('ready')}>
            查看待应用
          </button>
        </div>
      )}

      {/* 筛选 + 搜索 */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="收藏状态筛选">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
              className={`${chip} ${filter === key ? chipActive : chipIdle}`}
            >
              {label}
              <span className="ml-1 tabular-nums">{counts[key]}</span>
            </button>
          ))}
        </div>
        <input
          type="search"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="搜索名称 / 代码"
          aria-label="搜索收藏的股票名称或代码"
          className="ml-auto w-44 rounded border border-rule-strong bg-paper px-3 py-1.5 text-sm text-ink focus:outline-none focus:border-accent"
        />
      </div>

      {/* 任务进度/提示 */}
      {(pollError || valuationMessage || notice) && (
        <p role="status" className="text-sm text-ink">
          {pollError && <span className="text-amber-700">估值进度查询失败，任务不受影响，自动重试中… </span>}
          {valuationMessage}
          {jobProgress && <span className="ml-2 text-ink-muted">（{jobProgress.processed}/{jobProgress.total}）</span>}
          {valuationMessage && job && (job.status === 'partial_failed' || job.status === 'failed') && job.failed_codes.length > 0 && (
            <button className={`${ghostBtn} ml-2`} disabled={!configured} onClick={() => void submitEvaluate(job.failed_codes)}>
              重试失败 {job.failed_codes.length} 只
            </button>
          )}
          {notice && <span className="ml-2 text-emerald-700">{notice}</span>}
        </p>
      )}
      {!configured && (
        <p className="text-sm text-ink-muted">Hermes 未配置（需 HERMES_BASE_URL 与 HERMES_API_KEY），暂无法提交估值；阅读与手动挡位设置不受影响。</p>
      )}

      {/* 主表 */}
      <div className="overflow-x-auto rounded-xl border border-rule bg-paper-card">
        <table className="w-full text-sm text-ink whitespace-nowrap">
          <thead className="bg-paper-deep text-left">
            <tr>
              <th className="p-3 font-medium">股票 / 基本面</th>
              <th className="p-3 font-medium">现价（元）</th>
              <th className="p-3 font-medium">挡位（元）</th>
              <th className="p-3 font-medium">评估与监控状态</th>
              <th className="p-3 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {visible.map(row => (
              <TrackingRow
                key={row.code}
                row={row}
                qualityScore={qualityScores[row.code] ?? null}
                qualityVersion={qualityVersion}
                priceUpdatedAt={priceUpdatedAt}
                evaluating={(perCode[row.code]?.state === 'queued' || perCode[row.code]?.state === 'running') || actionPending === row.code}
                togglePending={actionPending === row.code}
                configured={configured}
                onEvaluate={() => void submitEvaluate([row.code])}
                onOpenReport={() => openReport(row.code)}
                onToggleEnabled={enabled => void handleToggleEnabled(row.code, enabled)}
                onOpenSettings={() => onOpenAlertSettings(row.code)}
              />
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={5} className="p-10 text-center text-ink-muted">
                  {rows.length === 0
                    ? '还没有收藏的股票，去「全部」或「选股关注」添加收藏。'
                    : '没有符合条件的收藏股，试试其他状态或搜索词。'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">
        显示 {visible.length} / {rows.length} 只收藏 · 待应用包含仍在使用旧挡位监控的股票 · 评估完成后由你确认应用
      </p>

      {/* 报告面板 */}
      <ValuationReportModal
        isOpen={!!reportModalRecord}
        onClose={() => { setReportCode(null); setApplyError(''); }}
        report={reportModalRecord}
        effectiveLevels={reportModalEffective}
        currentSkillVersion={currentSkillVersion}
        onApply={handleApply}
        onReevaluate={code => { setReportCode(null); void submitEvaluate([code]); }}
        applyPending={actionPending === reportModalCode}
        applyError={applyError}
      />
    </section>
  );
}

function TrackingRow({
  row,
  qualityScore,
  qualityVersion,
  priceUpdatedAt,
  evaluating,
  togglePending,
  configured,
  onEvaluate,
  onOpenReport,
  onToggleEnabled,
  onOpenSettings,
}: {
  row: {
    code: string;
    stock: DividendStockWithTechnical;
    alertItem?: { enabled: boolean; levels?: AlertLevels | null; updated_at?: string | null } | null;
    report: ValuationReportRecord | null;
    derived: FavoriteTrackingDerived;
    currentPrice: number | null;
    price?: { pe?: number | null; pb?: number | null; yield_ttm?: number | null } | null;
    liveError: string | null;
  };
  qualityScore: { dimensions: Record<QualityDimensionKey, number | null>; skill_version?: string | null } | null;
  qualityVersion: string | null;
  priceUpdatedAt: string | null;
  evaluating: boolean;
  togglePending: boolean;
  configured: boolean;
  onEvaluate: () => void;
  onOpenReport: () => void;
  onToggleEnabled: (enabled: boolean) => void;
  onOpenSettings: () => void;
}) {
  const { stock, alertItem, report, derived, currentPrice, price, liveError } = row;
  const meta = TRACKING_STATE_META[derived.state];
  const evaluatingNow = derived.state === 'evaluating' || evaluating;
  const levels = alertItem?.levels ?? null;
  const candidateLevels = derived.state === 'pending_apply' && report?.levels
    ? reportLevelsToAlertLevels(report.levels)
    : null;

  const statePill = (() => {
    if (evaluatingNow) {
      return <span className="inline-flex items-center gap-1 rounded bg-paper-tint px-1.5 py-0.5 text-xs text-info animate-pulse">评估中</span>;
    }
    const tone = derived.state === 'monitoring' ? 'bg-emerald-50 text-emerald-700'
      : derived.state === 'pending_apply' ? 'bg-amber-50 text-amber-700'
        : derived.state === 'failed' ? 'bg-red-50 text-red-700'
          : 'bg-paper-tint text-ink-muted';
    return (
      <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs ${tone}`}>
        {derived.state === 'monitoring' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-600" />}
        {meta.label}
      </span>
    );
  })();

  return (
    <tr className="border-t border-rule align-top hover:bg-paper-tint/60" data-code={stock.code}>
      {/* 股票 / 基本面 */}
      <td className="p-3">
        <div className="font-medium text-ink">{stock.name}</div>
        <div className="text-xs text-ink-muted">{stock.code} · {stock.sw_level1 || '—'}</div>
        {qualityScore ? (
          <div className="mt-0.5 text-xs text-ink-muted" title={QUALITY_DIMENSION_ORDER.map(key => `${QUALITY_DIMENSION_LABELS[key]} ${qualityScore.dimensions[key] ?? '未评分'}`).join(' / ')}>
            {QUALITY_DIMENSION_ORDER.map(key => qualityScore.dimensions[key] ?? '—').join('/')}
            <span className="ml-1">{qualityScore.skill_version ? `v${qualityScore.skill_version}` : (qualityVersion ? '需重评' : '')}</span>
          </div>
        ) : (
          <div className="mt-0.5 text-xs text-ink-muted">基本面未评级</div>
        )}
      </td>

      {/* 现价 */}
      <td className="p-3">
        {currentPrice != null ? (
          <>
            <div className="font-mono font-semibold tabular-nums">{currentPrice.toFixed(2)}</div>
            <div className="text-[10px] font-mono text-ink-muted tabular-nums">
              PE {price?.pe != null ? price.pe.toFixed(1) : '—'} · PB {price?.pb != null ? price.pb.toFixed(2) : '—'}
            </div>
          </>
        ) : (
          <span className="text-xs text-ink-muted">现价缺失</span>
        )}
        {priceUpdatedAt && (
          <div
            className="text-[10px] text-ink-muted mt-0.5"
            title={`现价数据更新于 ${new Date(priceUpdatedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}`}
          >
            已更新
          </div>
        )}
      </td>

      {/* 挡位条 */}
      <td className="p-3">
        {(() => {
          if (!levels) return null;
          const levelCount = VALUATION_LEVEL_KEYS.filter(key => levels[key]?.price).length;
          if (levelCount >= 2) {
            return <ValuationPriceBar levels={levels} currentPrice={currentPrice} variant="effective" title="当前生效挡位" />;
          }
          // 单挡位（手工配置可能只填一档）：不足两条价格线不画条，明确列出该档
          const only = VALUATION_LEVEL_KEYS.map(key => levels[key]).find(lv => lv?.price);
          return (
            <div className="text-xs text-ink-muted max-w-[220px] whitespace-normal">
              单挡位 ¥{only?.price.toFixed(2)}（仅一条价格线，不足画图条）
            </div>
          );
        })()}
        {!levels && candidateLevels && (
          <ValuationPriceBar levels={candidateLevels} currentPrice={currentPrice} variant="candidate" title="评估结果预览，尚未应用" />
        )}
        {!levels && !candidateLevels && (
          <div className="text-xs text-ink-muted max-w-[220px] whitespace-normal">
            {evaluatingNow
              ? '评估进行中，完成后在此显示价格挡位'
              : derived.state === 'failed'
                ? `评估失败${liveError ? `：${liveError}` : ''}，可重试`
                : report && report.status !== 'ready'
                  ? `${VALUATION_STATUS_LABEL[report.status]}：${report.summary.slice(0, 40)}${report.summary.length > 40 ? '…' : ''}`
                  : '尚未评估，先评估挡位再决定是否开启监控'}
          </div>
        )}
      </td>

      {/* 状态 */}
      <td className="p-3">
        {statePill}
        <div className="mt-1 text-xs text-ink-muted max-w-[180px] whitespace-normal">{meta.note}</div>
        {report && derived.state !== 'evaluating' && (
          <div className="mt-1 text-[10px] text-ink-muted">
            最近评估 {new Date(report.evaluated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
          </div>
        )}
        {derived.pendingApply && (
          <div className="mt-1 text-xs text-accent">新评估待应用 · 旧挡位持续生效</div>
        )}
      </td>

      {/* 操作 */}
      <td className="p-3">
        <div className="flex flex-col items-start gap-1.5">
          {evaluatingNow ? (
            <button type="button" className={ghostBtn} disabled>评估中…</button>
          ) : derived.pendingApply ? (
            <button type="button" className={primaryBtn} onClick={onOpenReport}>
              {derived.effective ? '对比并应用' : '查看并应用'}
            </button>
          ) : derived.state === 'unevaluated' ? (
            <button type="button" className={primaryBtn} disabled={!configured} title={configured ? '调用 Hermes 四挡位估值（约几分钟）' : 'Hermes 未配置'} onClick={onEvaluate}>
              评估挡位
            </button>
          ) : derived.state === 'failed' ? (
            <button type="button" className={primaryBtn} disabled={!configured} onClick={onEvaluate}>重试评估</button>
          ) : null}

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {report && (
              <button type="button" className={linkBtn} onClick={onOpenReport}>
                {derived.state === 'not_ready' ? '查看缺口' : '查看报告'}
              </button>
            )}
            {(derived.state === 'not_ready' || ((derived.state === 'monitoring' || derived.state === 'paused') && report)) && !evaluatingNow && (
              <button type="button" className={linkBtn} disabled={!configured} onClick={onEvaluate}>
                重新评估
              </button>
            )}
            {(derived.state === 'monitoring' || derived.state === 'paused') && (
              <button type="button" className={linkBtn} disabled={togglePending}
                onClick={() => onToggleEnabled(derived.state === 'paused')}>
                {derived.state === 'paused' ? '恢复监控' : '暂停'}
              </button>
            )}
            <button type="button" className={linkBtn} onClick={onOpenSettings}>挡位设置</button>
          </div>
        </div>
      </td>
    </tr>
  );
}
