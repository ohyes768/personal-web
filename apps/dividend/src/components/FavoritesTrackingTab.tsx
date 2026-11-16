/**
 * FavoritesTrackingTab — 收藏跟踪（替换原「挡位监控」Tab，?tab=alerts URL 保持兼容）
 *
 * 展示全部收藏（不限于已配置挡位），三种筛选 + 名称/代码搜索：
 *   全部收藏 / 待评估（还没出过可用价格）/ 待应用（可与已有生效挡位重叠）
 *
 * 行内七列：
 *   股票 │ 基本面 │ 现价 │ 挡位 │ 区间 │ 评估 │ 操作
 * - 「基本面」列：评分一行、版本一行；未评级时空态按钮直接发起分析
 *   （口径与筛选页一致：排队/评级中→进行中提示，失败→失败+重试+会话下载）。
 * - 「评估」列只讲最近一次 attempt：状态徽章 + 这次尝试的时间/版本 + 会话下载。
 *   四者永远指向同一次尝试，不再出现「下载的是失败那次、时间写的是上次成功那次」。
 * - 「挡位」列只画一条生效条；候选那套价不占表格宽度，由「应用」确认卡与
 *   独立阅读页 /valuation-reader 承载。
 * - 「操作」列单行按钮组：评估/重试/再评估 + 应用 + 挡位设置。
 */
'use client';

import { useCallback, useMemo, useState } from 'react';
import { dividendApi } from '@/lib/api';
import { useQualityAnalysis } from '@/lib/hooks/useQualityAnalysis';
import { useValuation } from '@/lib/hooks/useValuation';
import { isQualityPending, QUALITY_DIMENSION_LABELS, QUALITY_DIMENSION_ORDER, type QualityDimensionKey, type QualityPerCodeStatus } from '@/lib/quality';
import {
  VALUATION_EVAL_STATE_META,
  VALUATION_LEVEL_KEYS,
  VALUATION_LEVEL_LABEL,
  VALUATION_STATUS_LABEL,
  VALUATION_ZONE_COLOR,
  VALUATION_ZONE_LABEL,
  VALUATION_ZONE_TEXT_COLOR,
  buildValuationQueue,
  deriveFavoriteTrackingState,
  deriveTrackingActions,
  deriveValuationAttempt,
  deriveValuationEvalState,
  isAttemptRunning,
  matchesTrackingFilter,
  reportLevelsToAlertLevels,
  resolveValuationZone,
  resolveZoneSteps,
  type FavoriteTrackingDerived,
  type TrackingActions,
  type ValuationAttempt,
  type ValuationPerCodeItem,
  type TrackingFilterKey,
  type ValuationReportRecord,
} from '@/lib/valuation';
import type { AlertLevels, DividendStockWithTechnical, PriceItem } from '@/lib/types';
import type { UseAlertsStatusResult } from '@/lib/hooks/useAlertsStatus';
import type { UseWatchlistResult } from '@/lib/hooks/useWatchlist';
import { QualityQueuePanel } from './QualityQueuePanel';
import { QualitySkillVersion } from './QualitySkillVersion';
import { SessionDownloadButton } from './SessionDownloadButton';
import { ValuationApplyConfirm } from './ValuationApplyConfirm';
import { ValuationPriceBar } from './ValuationPriceBar';
import { ValuationReaderEntry } from './ValuationReaderEntry';
import { Modal } from './shared-ui/Modal';

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
/**
 * 操作列主按钮的统宽：4 个中文字（12px）+ px-3 内边距 = 72px。
 * 「评估挡位 / 重试评估 / 再评估 / 应用」字��数不同（2~4），不定宽的话同一列里
 * 按钮参差不齐；给最小宽度后短文案也补到 72px，整列对得上。
 */
const BTN_SLOT = 'min-w-[4.5rem] inline-flex items-center justify-center';
const primaryBtn = `rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50 ${BTN_SLOT}`;

function normalize(keyword: string): string {
  return keyword.trim().toLowerCase();
}

/** MM-DD HH:mm（自己拼格式，不走 toLocaleString：各浏览器 locale 的分隔符不一致） */
function formatMoment(iso: string | null | undefined): string {
  if (!iso) return '—';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(at.getMonth() + 1)}-${pad(at.getDate())} ${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

export function FavoritesTrackingTab({
  watchlist,
  stocks,
  alertsStatus,
  priceMap,
  priceUpdatedAt,
  onOpenAlertSettings,
  sourceQuery,
}: {
  watchlist: UseWatchlistResult;
  stocks: DividendStockWithTechnical[];
  alertsStatus: UseAlertsStatusResult;
  /** 现价（page 级 useRealtimePrices 统一拉取，避免与本组件重复请求） */
  priceMap: Map<string, PriceItem>;
  priceUpdatedAt: string | null;
  onOpenAlertSettings: (code: string) => void;
  /** 主页面当前 query（回跳阅读页时还原视图） */
  sourceQuery: string;
}) {
  const [filter, setFilter] = useState<TrackingFilterKey>('all');
  const [searchInput, setSearchInput] = useState('');
  const [applyCode, setApplyCode] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [applyError, setApplyError] = useState('');
  /** 再评估覆盖待应用报告的确认（待确认的股票代码） */
  const [confirmReevaluate, setConfirmReevaluate] = useState<{ code: string; name: string } | null>(null);

  const { reports, perCode, configured, currentSkillVersion, job, message: valuationMessage, pollError,
          analyze, refresh: refreshValuation, cancelQueueItem, moveQueueItem } = useValuation();
  const { qualityScores, qualityPerCode, qualityConfigured, currentSkillVersion: qualityVersion, analyze: analyzeQuality } = useQualityAnalysis();
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
        alertItem?.levels ?? null,
        alertItem?.updated_at ?? null,
        report,
        live,
      );
      const price = priceMap.get(code);
      const currentPrice = price?.realtime ?? price?.close ?? null;
      // 最近一次尝试（成功或失败）：状态、时间、版本、会话 run_id 四者同源
      const attempt = deriveValuationAttempt(report, live);
      return {
        code, stock, alertItem, report, derived, currentPrice, price,
        attempt,
        perCodeItem: live,
        actions: deriveTrackingActions(attempt, derived),
        /** 生效挡位最后一次写入时间（应用或手工编辑） */
        effectiveUpdatedAt: alertItem?.updated_at ?? null,
      };
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

  const submitEvaluate = useCallback(async (codeList: string[]) => {
    if (!codeList.length) return;
    setActionPending(codeList.join(','));
    await analyze(codeList);
    setActionPending(null);
  }, [analyze]);

  /** 行内「评估 / 重试评估 / 再评估」：有待应用报告时先确认覆盖 */
  const requestEvaluate = useCallback((code: string) => {
    const row = rows.find(r => r.code === code);
    if (row?.derived.pendingApply) {
      setConfirmReevaluate({ code, name: row.stock.name });
      return;
    }
    void submitEvaluate([code]);
  }, [rows, submitEvaluate]);

  const confirmReevaluateAndRun = useCallback(async () => {
    const target = confirmReevaluate;
    setConfirmReevaluate(null);
    if (!target) return;
    await submitEvaluate([target.code]);
  }, [confirmReevaluate, submitEvaluate]);

  const handleApply = useCallback(async (report: ValuationReportRecord) => {
    setApplyError('');
    setActionPending(report.code);
    try {
      await dividendApi.applyValuationReport(report.code, report.evaluated_at);
      await Promise.all([alertsStatus.refresh(), refreshValuation()]);
      setNotice(`${report.name} 挡位已应用，监控已开启`);
      setApplyCode(null);
    } catch (err) {
      const text = err instanceof Error ? err.message : '应用失败，请重试';
      setApplyError(text);
    } finally {
      setActionPending(null);
    }
  }, [alertsStatus, refreshValuation]);

  /** 行内「应用」的确认步骤（紧凑确认卡） */
  const openApplyConfirm = useCallback((code: string) => {
    setApplyError('');
    setApplyCode(code);
  }, []);

  const applyModalCode = applyCode;
  const applyModalRecord = applyModalCode ? reports[applyModalCode] ?? null : null;
  const applyModalEffective: AlertLevels | null = applyModalCode
    ? (alertsStatus.alertMap.get(applyModalCode)?.levels ?? null)
    : null;
  const applyModalPrice = applyModalCode ? (priceMap.get(applyModalCode)?.realtime ?? priceMap.get(applyModalCode)?.close ?? null) : null;
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
            <span className="text-ink-muted"> · 包含首次评估与已有挡位后的新评估，应用前旧挡位持续生效</span>
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
          {rows.length} 只收藏
          {pendingApplyCount > 0 && <span className="text-accent font-medium"> · {pendingApplyCount} 份待确认</span>}
        </p>
        <QualityQueuePanel view={valuationQueueView} onCancel={cancelQueueItem} onMove={moveQueueItem} label="估值" />
        <ValuationReaderEntry sourceQuery={sourceQuery} variant="toolbar" />
        <input
          type="search"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="搜索名称 / 代码"
          aria-label="搜索收藏的股票名称或代码"
          className="w-44 rounded border border-rule-strong bg-paper px-3 py-2 text-sm text-ink focus:outline-none focus:border-accent"
        />
      </div>

      {/* 任务进度/提示 */}
      {(pollError || valuationMessage || notice) && (
        <p role="status" className="text-sm text-ink">
          {pollError && <span className="text-amber-700">估值进度查询失败，任务不受影响，自动重试中… </span>}
          {valuationMessage}
          {jobProgress && <span className="ml-2 text-ink-muted">（{jobProgress.processed}/{jobProgress.total}）</span>}
          {valuationMessage && job && (job.status === 'partial_failed' || job.status === 'failed') && job.failed_codes.length > 0 && (
            <button type="button" className={`${ghostBtn} ml-2`} disabled={!configured} onClick={() => void submitEvaluate(job.failed_codes)}>
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
              <th className="p-3 font-medium">股票</th>
              <th className="p-3 font-medium" title="基本面评级：各维度评分与所用评分技能版本">基本面</th>
              <th className="p-3 font-medium">现价（元）</th>
              <th className="p-3 font-medium min-w-[500px]" title="四挡位价格条（本表加宽到 480px）">挡位（元）</th>
              <th className="p-3 font-medium" title="现价落在哪一区，以及再涨/跌多少会改变告警动作">区间</th>
              <th className="p-3 font-medium" title="最近一次评估的状态、时间与版本；会话记录可下载排查">评估</th>
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
                qualityLive={qualityPerCode[row.code] ?? null}
                qualityConfigured={qualityConfigured}
                onAnalyzeQuality={() => void analyzeQuality([row.code])}
                valuationVersion={currentSkillVersion}
                priceUpdatedAt={priceUpdatedAt}
                evaluating={actionPending === row.code}
                configured={configured}
                sourceQuery={sourceQuery}
                onEvaluate={() => requestEvaluate(row.code)}
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

      {/* 应用确认卡：行内「应用」的确认步骤 */}
      <ValuationApplyConfirm
        isOpen={!!applyModalRecord}
        onClose={() => { setApplyCode(null); setApplyError(''); }}
        report={applyModalRecord}
        effectiveLevels={applyModalEffective}
        currentPrice={applyModalPrice}
        onApply={handleApply}
        applyPending={actionPending === applyModalCode}
        applyError={applyError}
      />

      {/* 再评估覆盖待应用报告：确认后才提交 */}
      <Modal
        isOpen={!!confirmReevaluate}
        onClose={() => setConfirmReevaluate(null)}
        title="确认重新评估"
        size="sm"
        footer={(
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              className="rounded border border-rule-strong px-3 py-1.5 text-sm text-ink hover:bg-paper-tint"
              onClick={() => setConfirmReevaluate(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="rounded bg-accent px-3.5 py-1.5 text-sm font-medium text-white hover:opacity-90"
              onClick={() => void confirmReevaluateAndRun()}
            >
              确认重新评估
            </button>
          </div>
        )}
      >
        <p className="text-sm text-ink">
          重新评估会覆盖 {confirmReevaluate?.name} 当前待应用的报告（尚未生效），已生效的挡位不受影响。
        </p>
      </Modal>
    </section>
  );
}

function TrackingRow({
  row,
  qualityScore,
  qualityVersion,
  qualityLive,
  qualityConfigured,
  valuationVersion,
  priceUpdatedAt,
  evaluating,
  configured,
  sourceQuery,
  onEvaluate,
  onOpenApplyConfirm,
  onOpenSettings,
  onAnalyzeQuality,
}: {
  row: {
    code: string;
    stock: DividendStockWithTechnical;
    alertItem?: { levels?: AlertLevels | null; updated_at?: string | null } | null;
    report: ValuationReportRecord | null;
    derived: FavoriteTrackingDerived;
    currentPrice: number | null;
    price?: { pe?: number | null; pb?: number | null; yield_ttm?: number | null } | null;
    /** 最近一次评估尝试（成功或失败） */
    attempt: ValuationAttempt;
    /** 生效挡位最后一次写入时间 */
    effectiveUpdatedAt: string | null;
    actions: TrackingActions;
    perCodeItem: ValuationPerCodeItem | null;
  };
  qualityScore: { dimensions: Record<QualityDimensionKey, number | null>; skill_version?: string | null } | null;
  qualityVersion: string | null;
  /** 这只股票的评级实时状态（queued/running/failed 等），用于空态按钮分支 */
  qualityLive: QualityPerCodeStatus | null;
  /** Hermes 评级是否已配置；false 时置灰分析按钮 */
  qualityConfigured: boolean;
  /** 发起基本面评级分析 */
  onAnalyzeQuality: () => void;
  /** 当前已部署的估值 skill 版本；与行报告版本不一致时提示需重评 */
  valuationVersion: string | null;
  priceUpdatedAt: string | null;
  evaluating: boolean;
  configured: boolean;
  /** 主页面当前 query（阅读页回跳时还原视图） */
  sourceQuery: string;
  onEvaluate: () => void;
  onOpenApplyConfirm: () => void;
  onOpenSettings: () => void;
}) {
  const { stock, alertItem, report, derived, currentPrice, price, attempt, actions } = row;
  // 状态列只讲评估（监控开关不在这列：那是推送设置，不是评估结果）
  const evalState = deriveValuationEvalState(derived, row.perCodeItem);
  const evalMeta = VALUATION_EVAL_STATE_META[evalState];
  // 徽章已经说清的状态不再补一句说明（避免每行固定多占一行）。
  // 失败尤其不补：后端原文可能很长（如「run xxx 超过 3600s 未完成（最后状态 running）」），
  // 直接渲染会把行撑高——原文留在徽章的悬停提示里。
  const needsNote = evalState === 'cancelled'
    || evalState === 'not_ready'
    || (evalState === 'pending_apply' && !derived.effective);
  const evaluatingNow = isAttemptRunning(attempt.state) || evaluating;
  const evalNote = evalState === 'cancelled' ? '本次评估被取消，可重新评估'
    : evalState === 'not_ready' ? '未生成价格，可查看原因'
      : '';
  const levels = alertItem?.levels ?? null;
  const candidateLevels = derived.pendingApply && report?.levels
    ? reportLevelsToAlertLevels(report.levels)
    : null;

  /** 「评估」列第一行的时间部分：这次 attempt 的时间（版本不占文字，进「查看报告」悬停） */
  const attemptLine = (() => {
    if (evalState === 'manual') {
      // 只有手工挡位：从没走过 Hermes，时间是挡位最后写入时间
      // 「配置于」不占文字：徽章已是「手工挡位」，前缀进悬停，与其他行的时间口径一致
      return (
        <span className="tabular-nums" title={`挡位配置于 ${formatMoment(row.effectiveUpdatedAt)}`}>
          {formatMoment(row.effectiveUpdatedAt)}
        </span>
      );
    }
    if (isAttemptRunning(attempt.state)) {
      // 排队/运行的状态由徽章说清（排队含位次），这里只留时间
      return <span className="tabular-nums">{attempt.at ? formatMoment(attempt.at) : '—'}</span>;
    }
    if (attempt.state === 'failed' || attempt.state === 'cancelled') {
      // 失败/取消已由左侧徽章表达，时间旁不重复（取消时徽章也显示「已取消」）
      return <span className="tabular-nums">{formatMoment(attempt.at)}</span>;
    }
    if (attempt.state === 'completed' && attempt.at) {
      const outdated = !!valuationVersion && attempt.skillVersion && attempt.skillVersion !== valuationVersion;
      return (
        <span className="tabular-nums">
          {formatMoment(attempt.at)}
          {outdated && (
            <span className="ml-1 text-amber-700" title={`当前已部署 v${valuationVersion}，可重评`}>需重评</span>
          )}
        </span>
      );
    }
    return <span>—</span>;
  })();

  /** 「查看报告」的悬停：版本 + 评估时间是这份报告的溯源，不占行内高度 */
  const reportLinkTitle = attempt.at
    ? `查看报告${attempt.skillVersion ? ` · v${attempt.skillVersion}` : ''} · 评估于 ${formatMoment(attempt.at)}`
    : undefined;

  /** 会话下载：与上面这次 attempt 同源（成功/失败/取消都能下）；
      行内用短文案「会话」，完整说明在悬停里 */
  const sessionBlock = attempt.runId ? (
    <span title={attempt.state === 'failed'
      ? `评估失败，可下载本次 Hermes 会话排查：${attempt.error ?? '未知原因'}`
      : attempt.state === 'cancelled'
        ? '本次评估被取消，可下载会话记录复盘'
        : '下载本次评估的 Hermes 会话记录'}>
      <SessionDownloadButton runId={attempt.runId} download={dividendApi.downloadValuationSession} label="会话" />
    </span>
  ) : null;

  // 「区间」列：当前所在区 + 到下一个会改变告警动作的价格线还有多远。
  // 口径见 resolveValuationZone / resolveZoneSteps（与后端 AlertService 一致）。
  const zoneInfo = useMemo(() => {
    const source = levels ?? candidateLevels;
    if (!source || currentPrice == null) return null;
    const zone = resolveValuationZone(source, currentPrice);
    return {
      zone,
      steps: resolveZoneSteps(source, currentPrice),
    };
  }, [levels, candidateLevels, currentPrice]);

  const evalPill = (() => {
    if (isAttemptRunning(attempt.state)) {
      // 排队与运行分开说：排队带位次，运行才叫「评估中」，不再上下两行互相打架
      return attempt.state === 'queued'
        ? <span className="inline-flex items-center gap-1 rounded bg-paper-tint px-1.5 py-0.5 text-xs text-ink-muted animate-pulse" data-eval-state="evaluating">{attempt.position ? `排队中 · 第 ${attempt.position} 位` : '排队中'}</span>
        : <span className="inline-flex items-center gap-1 rounded bg-paper-tint px-1.5 py-0.5 text-xs text-info animate-pulse" data-eval-state="evaluating">评估中</span>;
    }
    if (evaluatingNow && evalState !== 'failed') {
      return <span className="inline-flex items-center gap-1 rounded bg-paper-tint px-1.5 py-0.5 text-xs text-info animate-pulse">评估中</span>;
    }
    const tone = evalMeta.tone === 'ok' ? 'bg-emerald-50 text-emerald-700'
      : evalMeta.tone === 'warn' ? 'bg-amber-50 text-amber-700'
        : evalMeta.tone === 'bad' ? 'bg-red-50 text-red-700'
          : 'bg-paper-tint text-ink-muted';
    // 失败原因原文可能很长，列表不渲染，只留在徽章的悬停提示里
    const errorTitle = evalState === 'failed' && attempt.error
      ? `评估失败：${attempt.error}`
      : undefined;
    return (
      <span
        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs ${tone}`}
        data-eval-state={evalState}
        title={errorTitle}
      >
        {evalState === 'succeeded' && <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-600" />}
        {evalMeta.label}
      </span>
    );
  })();

  /** 评估类按钮：文案随「有没有评估过 / 失败没成」变化 */
  const evaluateButton = (() => {
    if (actions.evaluate === 'running') {
      // 评估中也是同一个按钮位，宽度跟着主按钮走（否则行一开跑按钮就缩一下）
      return <button type="button" className={`${ghostBtn} ${BTN_SLOT}`} disabled>评估中…</button>;
    }
    if (actions.evaluate === 'evaluate') {
      return (
        <button type="button" className={primaryBtn} disabled={!configured} title={configured ? '调用 Hermes 四挡位估值（约几分钟）' : 'Hermes 未配置'} onClick={onEvaluate}>
          评估挡位
        </button>
      );
    }
    if (actions.evaluate === 'retry') {
      return (
        <button type="button" className={primaryBtn} disabled={!configured} title={configured ? '重试这次失败的估值' : 'Hermes 未配置'} onClick={onEvaluate}>
          重试评估
        </button>
      );
    }
    if (actions.evaluate === 'reevaluate') {
      return (
        <button type="button" className={primaryBtn} disabled={!configured} title={configured ? '用 Hermes 重新评估这一只（约几分钟）' : 'Hermes 未配置'} onClick={onEvaluate}>
          再评估
        </button>
      );
    }
    return null;
  })();

  return (
    <tr className="border-t border-rule align-top hover:bg-paper-tint/60" data-code={stock.code}>
      {/* 股票 */}
      <td className="p-3">
        <div className="font-medium text-ink">{stock.name}</div>
        <div className="text-xs text-ink-muted">{stock.code} · {stock.sw_level1 || '—'}</div>
      </td>

      {/* 基本面评级：评分一行、版本一行；未评级时空态按钮直接发起分析
          （口径与筛选页一致：排队/评级中→进行中提示，失败→失败+重试+会话下载） */}
      <td className="p-3">
        {qualityScore ? (
          <>
            <div
              className="text-xs tabular-nums"
              title={QUALITY_DIMENSION_ORDER.map(key => `${QUALITY_DIMENSION_LABELS[key]} ${qualityScore.dimensions[key] ?? '未评分'}`).join(' / ')}
            >
              {QUALITY_DIMENSION_ORDER.map(key => qualityScore.dimensions[key] ?? '—').join('/')}
            </div>
            <div className="text-xs text-ink-muted">
              <QualitySkillVersion version={qualityScore.skill_version} currentVersion={qualityVersion} />
            </div>
          </>
        ) : isQualityPending(qualityLive) ? (
          <span className="text-xs text-ink-muted animate-pulse" title="评级任务进行中，完成后自动刷新">
            {qualityLive?.state === 'queued' ? '排队中…' : '评级中…'}
          </span>
        ) : qualityLive?.state === 'failed' ? (
          <span className="inline-flex items-center gap-2">
            <span className="text-xs text-red-700" title={qualityLive.error || '评级失败'}>失败</span>
            <button type="button" className={ghostBtn} disabled={!qualityConfigured} title={qualityLive.error || '重新发起评级'} onClick={onAnalyzeQuality}>重试</button>
            {qualityLive.run_id && <SessionDownloadButton runId={qualityLive.run_id} download={dividendApi.downloadQualitySession} />}
          </span>
        ) : (
          <button
            type="button"
            className={ghostBtn}
            disabled={!qualityConfigured}
            title={qualityConfigured ? '对这只股票调用 AI 五维基本面评级（约几分钟）' : 'Hermes 未配置（需 HERMES_BASE_URL 与 HERMES_API_KEY），无法评级'}
            onClick={onAnalyzeQuality}
          >
            分析
          </button>
        )}
      </td>

      {/* 现价：一行价格、一行 PE、一行 PB（PE/PB 各占一行，不合并省宽度） */}
      <td className="p-3">
        {currentPrice != null ? (
          <>
            <div
              className="font-mono font-semibold tabular-nums"
              title={priceUpdatedAt ? `现价数据更新于 ${new Date(priceUpdatedAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}` : undefined}
            >
              {currentPrice.toFixed(2)}
            </div>
            <div className="font-mono text-[10px] text-ink-muted tabular-nums">
              PE {price?.pe != null ? price.pe.toFixed(1) : '—'}
            </div>
            <div className="font-mono text-[10px] text-ink-muted tabular-nums">
              PB {price?.pb != null ? price.pb.toFixed(2) : '—'}
            </div>
          </>
        ) : (
          <span className="text-xs text-ink-muted">现价缺失</span>
        )}
      </td>

      {/* 挡位条：只画一条（生效的），候选那套价由确认卡与阅读页承载 */}
      <td className="p-3">
        {(() => {
          if (levels) {
            const levelCount = VALUATION_LEVEL_KEYS.filter(key => levels[key]?.price).length;
            if (levelCount >= 2) {
              return (
                <>
                  <ValuationPriceBar
                    levels={levels}
                    currentPrice={currentPrice}
                    currentPE={price?.pe ?? null}
                    currentPB={price?.pb ?? null}
                    dividend2025={stock.dividend_2025 ?? null}
                    yieldTtm={price?.yield_ttm ?? null}
                    variant="effective"
                    title="当前生效挡位"
                    style={{ width: 480 }}
                  />
                  {/* 生效挡位的时间与版本都不写——报告按 code 覆盖写，候选报告成功后
                      旧报告已被顶掉，生效挡位当年用的哪版 skill 事后查不到；时间也可由
                      「评估」列的 attempt 时间推算，这里不再单独占一行。 */}
                </>
              );
            }
            // 单挡位（手工配置可能只填一档）：不足两条价格线不画条，明确列出该档
            const only = VALUATION_LEVEL_KEYS.map(key => levels[key]).find(lv => lv?.price);
            return (
              <div className="text-xs text-ink-muted max-w-[220px] whitespace-normal">
                单挡位 ¥{only?.price.toFixed(2)}（仅一条价格线，不足画图条）
              </div>
            );
          }
          if (candidateLevels) {
            return (
              <>
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
                {/* 待应用的时间与版本不在这里重复：「评估」列的溯源行（attemptLine）
                    已经写了这次 attempt 的时间和 v 版本，「待应用」状态也由评估徽章表达。 */}
              </>
            );
          }
          return (
            <div className="text-xs text-ink-muted max-w-[220px] whitespace-normal">
              {evaluatingNow
                ? '评估进行中，完成后在此显示价格挡位'
                : derived.state === 'failed'
                  // 失败原因已经在「评估状态」列显示；这里只说评估没出结果，不重复同一句话
                  ? '评估失败，暂无挡位'
                  : report && report.status !== 'ready'
                    ? `${VALUATION_STATUS_LABEL[report.status]}：${report.summary.slice(0, 40)}${report.summary.length > 40 ? '…' : ''}`
                    : '尚未评估，先评估挡位再决定是否设置'}
            </div>
          );
        })()}
      </td>

      {/* 区间：当前所在区 + 到下一个变盘线还有多远（口径同后端告警判定） */}
      <td className="p-3 align-top">
        {zoneInfo?.zone.zone ? (
          <div className="max-w-[152px] whitespace-normal" data-testid="valuation-zone">
            <span
              className="inline-flex items-center gap-1 text-xs font-semibold"
              style={{ color: VALUATION_ZONE_TEXT_COLOR[zoneInfo.zone.zone] }}
            >
              <span
                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: VALUATION_ZONE_COLOR[zoneInfo.zone.zone] }}
                aria-hidden
              />
              {VALUATION_ZONE_LABEL[zoneInfo.zone.zone]}
            </span>
            {zoneInfo.steps.map(step => (
              <div
                key={step.key}
                className="mt-0.5 whitespace-nowrap font-mono text-[10px] tabular-nums text-ink-muted"
                title={`再${step.direction === 'up' ? '涨' : '跌'} ${step.pct.toFixed(1)}% 到${VALUATION_LEVEL_LABEL[step.key]}线 ¥${step.price.toFixed(2)}`}
              >
                {step.direction === 'up' ? '↑' : '↓'}{VALUATION_LEVEL_LABEL[step.key]} {step.pct.toFixed(1)}%
              </div>
            ))}
          </div>
        ) : (
          <span className="text-xs text-ink-muted">—</span>
        )}
      </td>

      {/* 评估：第一行徽章 + 时间（同一次 attempt），第二行产物入口。
          版本不占文字：进「查看报告」悬停，仅「需重评」时在时间旁露文字。 */}
      <td className="p-3">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {evalPill}
          <span className="text-xs text-ink-muted">{attemptLine}</span>
        </div>
        {/* 这份评估的两个产物：报告正文与会话记录。放在评估列是因为它们讲的
            都是「这次评估」本身，不是对这只股票的动作 */}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          {actions.reportLinks.includes('view_report') && (
            <ValuationReaderEntry
              sourceQuery={sourceQuery}
              code={row.code}
              variant="inline"
              ariaLabel={`查看报告 · ${stock.name}`}
              title={reportLinkTitle}
            >
              查看报告
            </ValuationReaderEntry>
          )}
          {actions.reportLinks.includes('view_gaps') && (
            <ValuationReaderEntry
              sourceQuery={sourceQuery}
              code={row.code}
              variant="inline"
              ariaLabel={`查看缺口 · ${stock.name}`}
            >
              查看缺口
            </ValuationReaderEntry>
          )}
          {sessionBlock}
        </div>
        {needsNote && (
          <div className="mt-1 text-xs text-ink-muted max-w-[180px] whitespace-normal">{evalNote}</div>
        )}
        {derived.pendingApply && derived.effective && (
          <div className="mt-1 text-xs text-accent">新评估待应用 · 旧挡位仍生效</div>
        )}
      </td>

      {/* 操作：只放对这只股票的动作——评估/重试/再评估、应用、挡位设置。
          全部一行不换行：flex-wrap 会让挤压时按钮掉行、行高跳；nowrap 后
          这列的最小宽度固定为整组按钮宽，挤压由表格横向滚动消化。 */}
      <td className="p-3">
        <div className="flex flex-nowrap items-center gap-x-2">
          {evaluateButton}
          {actions.apply && (
            <button type="button" className={primaryBtn} onClick={onOpenApplyConfirm}>应用</button>
          )}
          {actions.links.includes('settings') && (
            <button type="button" className={ghostBtn} onClick={onOpenSettings} title="设置该股的挡位监控价格与开关">设置</button>
          )}
        </div>
      </td>
    </tr>
  );
}
