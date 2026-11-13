/**
 * FavoritesTrackingTab — 收藏跟踪（替换原「挡位监控」Tab，?tab=alerts URL 保持兼容）
 *
 * 展示全部收藏（不限于已配置挡位），三种筛选 + 名称/代码搜索：
 *   全部收藏 / 待评估（从未应用挡位且无待应用报告）/ 待应用（可与监控中/已暂停重叠）
 * 行内：评估挡位/重评/重试、待应用行分「应用」（紧凑确认卡）与「查看报告」（报告弹窗）、
 *   挡位设置（既有 AlertSettingsModal，启用监控的开关也收在这里）。
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
  VALUATION_LEVEL_LABEL,
  VALUATION_STATUS_LABEL,
  buildValuationQueue,
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
import { QualityQueuePanel } from './QualityQueuePanel';
import { ValuationApplyConfirm } from './ValuationApplyConfirm';
import { ValuationPriceBar } from './ValuationPriceBar';
import { ValuationReportModal } from './ValuationReportModal';

const FILTERS: Array<{ key: TrackingFilterKey; label: string }> = [
  { key: 'all', label: '全部收藏' },
  { key: 'pending', label: '待评估' },
  { key: 'ready', label: '待应用' },
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
  const [applyCode, setApplyCode] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [applyError, setApplyError] = useState('');

  const { reports, perCode, configured, currentSkillVersion, job, message: valuationMessage, pollError,
          analyze, refresh: refreshValuation, cancelQueueItem, moveQueueItem } = useValuation();
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
  const monitoringCount = rows.filter(row => row.derived.state === 'monitoring').length;

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
      setApplyCode(null);
    } catch (err) {
      const text = err instanceof Error ? err.message : '应用失败，请重试';
      setApplyError(text);
    } finally {
      setActionPending(null);
    }
  }, [alertsStatus, refreshValuation]);

  const openReport = useCallback((code: string) => {
    setApplyError('');
    setReportCode(code);
  }, []);

  /** 行内「应用」：打开确认卡（不经过报告弹窗） */
  const openApplyConfirm = useCallback((code: string) => {
    setApplyError('');
    setApplyCode(code);
  }, []);

  const reportModalCode = reportCode;
  const reportModalRecord = reportModalCode ? reports[reportModalCode] ?? null : null;
  const reportModalEffective: AlertLevels | null = reportModalCode
    ? (alertsStatus.alertMap.get(reportModalCode)?.levels ?? null)
    : null;
  const applyModalCode = applyCode;
  const applyModalRecord = applyModalCode ? reports[applyModalCode] ?? null : null;
  const applyModalEffective: AlertLevels | null = applyModalCode
    ? (alertsStatus.alertMap.get(applyModalCode)?.levels ?? null)
    : null;
  const jobProgress = job && (job.status === 'queued' || job.status === 'running')
    ? { processed: job.processed, total: job.total }
    : null;
  const valuationQueueView = useMemo(() => buildValuationQueue(perCode), [perCode]);

  return (
    <section aria-label="收藏跟踪" className="space-y-3">
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
        <p className="ml-auto text-xs text-ink-muted">
          {rows.length} 只收藏 · {monitoringCount} 只监控中
          {pendingApplyCount > 0 && <span className="text-accent font-medium"> · {pendingApplyCount} 份待确认</span>}
        </p>
        <QualityQueuePanel view={valuationQueueView} onCancel={cancelQueueItem} onMove={moveQueueItem} label="估值" />
        <input
          type="search"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="搜索名称 / 代码"
          aria-label="搜索收藏的股票名称或代码"
          className="w-44 rounded border border-rule-strong bg-paper px-3 py-1.5 text-sm text-ink focus:outline-none focus:border-accent"
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
              <th className="p-3 font-medium">评估 / 版本</th>
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
                valuationVersion={currentSkillVersion}
                priceUpdatedAt={priceUpdatedAt}
                evaluating={(perCode[row.code]?.state === 'queued' || perCode[row.code]?.state === 'running') || actionPending === row.code}
                configured={configured}
                onEvaluate={() => void submitEvaluate([row.code])}
                onOpenReport={() => openReport(row.code)}
                onOpenApplyConfirm={() => openApplyConfirm(row.code)}
                onOpenSettings={() => onOpenAlertSettings(row.code)}
              />
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={6} className="p-10 text-center text-ink-muted">
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

      {/* 应用确认卡：行内「应用」的确认步骤 */}
      <ValuationApplyConfirm
        isOpen={!!applyModalRecord}
        onClose={() => { setApplyCode(null); setApplyError(''); }}
        report={applyModalRecord}
        effectiveLevels={applyModalEffective}
        onApply={handleApply}
        applyPending={actionPending === applyModalCode}
        applyError={applyError}
      />
    </section>
  );
}

function TrackingRow({
  row,
  qualityScore,
  qualityVersion,
  valuationVersion,
  priceUpdatedAt,
  evaluating,
  configured,
  onEvaluate,
  onOpenReport,
  onOpenApplyConfirm,
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
  /** 当前已部署的估值 skill 版本；与行报告版本不一致时提示需重评 */
  valuationVersion: string | null;
  priceUpdatedAt: string | null;
  evaluating: boolean;
  configured: boolean;
  onEvaluate: () => void;
  onOpenReport: () => void;
  onOpenApplyConfirm: () => void;
  onOpenSettings: () => void;
}) {
  const { stock, alertItem, report, derived, currentPrice, price, liveError } = row;
  const currentValuationVersion = valuationVersion;
  const meta = TRACKING_STATE_META[derived.state];
  // 徽章已经说清的状态不再补一句说明（避免每行固定多占一行）
  const needsNote = derived.state === 'evaluating'
    || derived.state === 'failed'
    || derived.state === 'not_ready'
    || derived.state === 'paused'
    || (derived.state === 'pending_apply' && !derived.effective);
  const evaluatingNow = derived.state === 'evaluating' || evaluating;
  const levels = alertItem?.levels ?? null;
  const candidateLevels = derived.state === 'pending_apply' && report?.levels
    ? reportLevelsToAlertLevels(report.levels)
    : null;

  // 距各档距离（现价列）：距现价最近的一条价格线，含方向
  const distanceNote = useMemo(() => {
    const source = levels ?? candidateLevels;
    if (!source || currentPrice == null) return '';
    const priced = VALUATION_LEVEL_KEYS
      .map(key => ({ key, price: source[key]?.price }))
      .filter(item => item.price != null && item.price > 0)
      .map(item => ({
        key: item.key,
        price: item.price as number,
        pct: ((currentPrice - (item.price as number)) / (item.price as number)) * 100,
      }));
    if (!priced.length) return '';
    const nearest = priced.reduce((best, item) => (
      Math.abs(item.pct) < Math.abs(best.pct) ? item : best
    ));
    const sign = nearest.pct > 0 ? '+' : '';
    return `距${VALUATION_LEVEL_LABEL[nearest.key]} ${sign}${nearest.pct.toFixed(1)}%`;
  }, [levels, candidateLevels, currentPrice]);

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
            <div
              className="font-mono font-semibold tabular-nums"
              title={priceUpdatedAt ? `现价数据更新于 ${new Date(priceUpdatedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}` : undefined}
            >
              {currentPrice.toFixed(2)}
            </div>
            <div className="text-[10px] font-mono text-ink-muted tabular-nums">
              PE {price?.pe != null ? price.pe.toFixed(1) : '—'} · PB {price?.pb != null ? price.pb.toFixed(2) : '—'}
            </div>
            {/* 距各档距离：条上只表达位置关系，精确数字放现价列（行高由条决定，这里不额外加高） */}
            {distanceNote && (
              <div className="mt-0.5 text-[10px] font-mono text-ink-muted tabular-nums whitespace-normal max-w-[150px]">
                {distanceNote}
              </div>
            )}
          </>
        ) : (
          <span className="text-xs text-ink-muted">现价缺失</span>
        )}
      </td>

      {/* 挡位条 */}
      <td className="p-3">
        {(() => {
          if (!levels) return null;
          const levelCount = VALUATION_LEVEL_KEYS.filter(key => levels[key]?.price).length;
          if (levelCount >= 2) {
            return (
              <ValuationPriceBar
                levels={levels}
                currentPrice={currentPrice}
                currentPE={price?.pe ?? null}
                currentPB={price?.pb ?? null}
                dividend2025={stock.dividend_2025 ?? null}
                yieldTtm={price?.yield_ttm ?? null}
                variant="effective"
                title="当前生效挡位"
              />
            );
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
          <ValuationPriceBar
            levels={candidateLevels}
            currentPrice={currentPrice}
            currentPE={price?.pe ?? null}
            currentPB={price?.pb ?? null}
            dividend2025={stock.dividend_2025 ?? null}
            yieldTtm={price?.yield_ttm ?? null}
            variant="candidate"
            title="评估结果预览，尚未应用"
          />
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

      {/* 评估 / 版本：报告时间 + skill 版本；手工配置无报告时显示配置时间 */}
      <td className="p-3 text-xs text-ink-muted whitespace-nowrap">
        {report ? (
          <>
            <div className="tabular-nums">
              {new Date(report.evaluated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
            </div>
            <div className="mt-0.5 font-mono">
              {report.skill_version ? `v${report.skill_version}` : '版本未记录'}
              {currentValuationVersion && report.skill_version && report.skill_version !== currentValuationVersion && (
                <span className="ml-1 text-amber-700" title={`当前已部署 v${currentValuationVersion}，可重评`}>需重评</span>
              )}
            </div>
          </>
        ) : alertItem?.updated_at ? (
          <>
            <div className="tabular-nums">
              {new Date(alertItem.updated_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
            </div>
            <div className="mt-0.5">手工配置</div>
          </>
        ) : (
          '—'
        )}
      </td>

      {/* 状态：徽章说话；只有需要额外解释的状态才补一行（每行最多 3 行） */}
      <td className="p-3">
        {statePill}
        {needsNote && (
          <div className="mt-1 text-xs text-ink-muted max-w-[180px] whitespace-normal">{meta.note}</div>
        )}
        {derived.pendingApply && derived.effective && (
          <div className="mt-1 text-xs text-accent">新评估待应用 · 旧挡位仍生效</div>
        )}
      </td>

      {/* 操作：待应用行给两个并列动作（应用 / 查看报告），其余状态保持单入口。
          行内不再放「暂停/恢复监控」——启用监控改到「挡位设置」里勾选。 */}
      <td className="p-3">
        <div className="flex flex-col items-start gap-1.5">
          {evaluatingNow ? (
            <button type="button" className={ghostBtn} disabled>评估中…</button>
          ) : derived.pendingApply ? (
            <div className="flex items-center gap-1.5">
              <button type="button" className={primaryBtn} onClick={onOpenApplyConfirm}>应用</button>
              <button type="button" className={ghostBtn} onClick={onOpenReport}>查看报告</button>
            </div>
          ) : derived.state === 'unevaluated' ? (
            <button type="button" className={primaryBtn} disabled={!configured} title={configured ? '调用 Hermes 四挡位估值（约几分钟）' : 'Hermes 未配置'} onClick={onEvaluate}>
              评估挡位
            </button>
          ) : derived.state === 'failed' ? (
            <button type="button" className={primaryBtn} disabled={!configured} onClick={onEvaluate}>重试评估</button>
          ) : null}

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {report && !derived.pendingApply && (
              <button type="button" className={linkBtn} onClick={onOpenReport}>
                {derived.state === 'not_ready' ? '查看缺口' : '查看报告'}
              </button>
            )}
            {!report && (derived.state === 'monitoring' || derived.state === 'paused') && !evaluatingNow && (
              <button type="button" className={linkBtn} disabled={!configured} onClick={onEvaluate}>评估挡位</button>
            )}
            <button type="button" className={linkBtn} onClick={onOpenSettings}>挡位设置</button>
          </div>
        </div>
      </td>
    </tr>
  );
}
