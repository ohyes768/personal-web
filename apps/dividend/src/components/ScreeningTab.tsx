'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRealtimePrices } from '@/lib/hooks/useRealtimePrices';
import { useQualityAnalysis } from '@/lib/hooks/useQualityAnalysis';
import { dividendApi } from '@/lib/api';
import { buildQualityQueue, isQualityPending, QUALITY_DIMENSION_ORDER, QUALITY_DIMENSION_LABELS } from '@/lib/quality';
import { DEFAULT_SCREENING, restoreScreeningConditions, SCREENING_STORAGE_KEY, type ScreeningConditions, type ScreeningItem, type ScreeningResponse, type ScreeningStatus } from '@/lib/screening';
import type { UseWatchlistResult } from '@/lib/hooks/useWatchlist';
import { QualityReportModal } from './QualityReportModal';
import { QualityQueuePanel } from './QualityQueuePanel';
import { QualityReaderEntry } from './QualityReaderEntry';
import { ScreeningStockDetailModal } from './ScreeningStockDetailModal';
import { SessionDownloadButton } from './SessionDownloadButton';

const pct = (value?: number | null) => value == null || !Number.isFinite(value) ? '待补' : `${value.toFixed(2)}%`;
// 六字段全量序列化：防抖键，条件变化检测与持久化共用
const keyOfScreening = (c: ScreeningConditions) => JSON.stringify([c.min_yield, c.min_roe, c.min_roe_avg_3y, c.max_quarter_profit_decline_pct, c.min_cagr_3y, c.exchange ?? '']);
const formatTimestamp = (value?: string | null) => {
  if (!value) return '暂无记录';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};
const isDeclining = (value?: number | null) => value != null && Number.isFinite(value) && value < 0;
const isScreeningValid = (c: ScreeningConditions) => [c.min_yield, c.min_roe, c.min_roe_avg_3y].every(value => Number.isFinite(value) && value >= 0 && value <= 100) && Number.isFinite(c.max_quarter_profit_decline_pct) && c.max_quarter_profit_decline_pct > 0 && c.max_quarter_profit_decline_pct <= 100 && Number.isFinite(c.min_cagr_3y) && c.min_cagr_3y >= -100 && c.min_cagr_3y <= 100;
const statusNames: Record<ScreeningStatus, string> = { eligible: '符合条件', excluded: '未符合', insufficient_data: '待补数据' };
const buttonClass = 'rounded border border-rule-strong px-3 py-2 text-sm text-ink hover:border-accent disabled:opacity-40';

export function ScreeningTab({ watchlist, refreshRevision = 0, sourceQuery = 'tab=screening' }: { watchlist: UseWatchlistResult; refreshRevision?: number; sourceQuery?: string }) {
  const [conditions, setConditions] = useState<ScreeningConditions>(DEFAULT_SCREENING);
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<ScreeningStatus>('eligible');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [failedCodes, setFailedCodes] = useState<string[]>([]);
  /** 本次收藏新增的代码：给「评估挡位」快捷入口用（不自动提交） */
  const [lastAdded, setLastAdded] = useState<string[]>([]);
  const [quickNotice, setQuickNotice] = useState('');
  const [quickPending, setQuickPending] = useState(false);
  const [qualityModalCode, setQualityModalCode] = useState<string | null>(null);
  const [detailItem, setDetailItem] = useState<ScreeningItem | null>(null);
  const { qualityScores, qualityPerCode, qualityConfigured, currentSkillVersion, qualityJob, qualityMessage, qualityPollError, analyze, cancelQueueItem, moveQueueItem } = useQualityAnalysis();
  const queueView = buildQualityQueue(qualityPerCode);
  const pending = useCallback((code: string) => isQualityPending(qualityPerCode[code]), [qualityPerCode]);
  const requestId = useRef(0);
  const appliedConditions = useRef(DEFAULT_SCREENING);
  const previousRevision = useRef(refreshRevision);
  // 防抖键：记录已查询的条件；防抖触发时与最新键比对，相同则不重复发
  const conditionsKeyRef = useRef(keyOfScreening(conditions));
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 作废在途请求：序号 +1 后，先前发出的响应不再被采纳。
  // 抽成稳定回调，避免在 effect cleanup 里直接读 ref（cleanup 执行时 ref 可能已被改写）。
  const invalidateRequest = useCallback(() => { requestId.current++; }, []);
  const query = useCallback(async (next: ScreeningConditions) => {
    appliedConditions.current = next;
    const id = ++requestId.current;
    setLoading(true); setError(''); setMessage(''); setFailedCodes([]);
    // 自动重查（防抖）期间保留旧结果，避免整表闪烁消失；新响应到达后整体替换
    try {
      const response = await dividendApi.screenStocks(next);
      if (id === requestId.current) setResult(response);
    } catch (err) {
      if (id === requestId.current) setError(err instanceof Error ? err.message : '筛选失败');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  // 挂载只查一次：恢复本地条件（无则默认）并查询；防抖重查由 changeConditions 负责，挂载不经过它，天然无双发
  useEffect(() => {
    let next = { ...DEFAULT_SCREENING };
    try {
      next = restoreScreeningConditions(JSON.parse(localStorage.getItem(SCREENING_STORAGE_KEY) || 'null'));
    } catch { /* unavailable storage uses defaults */ }
    conditionsKeyRef.current = keyOfScreening(next);
    setConditions(next); void query(next);
    return () => { invalidateRequest(); };
  }, [query, invalidateRequest]);

  // 输入即生效：与「全部」tab 同一范式——条件变化停 350ms 后自动重查并持久化
  // （替代手动「查询候选」按钮与「条件已修改」警告条）。
  // 防抖闭包捕获显式 next 而非 state：挂载恢复 / 恢复默认都不经过它，不会误用首帧条件。
  const changeConditions = useCallback((next: ScreeningConditions) => {
    setConditions(next);
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!isScreeningValid(next)) return; // 输入中途（如清空）不查询，也不动防抖键
    const key = keyOfScreening(next);
    debounceTimer.current = setTimeout(() => {
      if (key === conditionsKeyRef.current) return; // 与上次查询同条件（如已是默认时点恢复默认）不重复发
      conditionsKeyRef.current = key;
      if (key === keyOfScreening(DEFAULT_SCREENING)) { try { localStorage.removeItem(SCREENING_STORAGE_KEY); } catch {} }
      else { try { localStorage.setItem(SCREENING_STORAGE_KEY, JSON.stringify(next)); } catch {} }
      void query(next);
    }, 350);
  }, [query]);
  // 组件卸载时清掉未触发的防抖
  useEffect(() => () => { if (debounceTimer.current) clearTimeout(debounceTimer.current); }, []);

  useEffect(() => {
    if (previousRevision.current !== refreshRevision) {
      previousRevision.current = refreshRevision;
      void query(appliedConditions.current);
    }
  }, [refreshRevision, query]);

  async function save(codes: string[]) {
    if (!codes.length) return;
    setSaving(true); setMessage(''); setFailedCodes([]); setQuickNotice('');
    try {
      const response = await dividendApi.addFavoritesBatch(codes);
      const failed = response.items.filter(item => item.status === 'failed');
      const added = response.items.filter(item => item.status === 'added').map(item => item.code);
      setFailedCodes(failed.map(item => item.code));
      setLastAdded(added);
      setMessage(`新增 ${added.length} 只，已收藏 ${response.items.filter(item => item.status === 'already_exists').length} 只，失败 ${failed.length} 只${failed.length ? '：' + failed.map(item => `${item.code} ${item.error || ''}`).join('；') : ''}`);
      setSelected(new Set(failed.map(item => item.code)));
      try { localStorage.setItem('watchlist-sync-tick', String(Date.now())); } catch { /* refresh still works */ }
      await watchlist.refresh();
    } catch (err) {
      setFailedCodes(codes);
      setLastAdded([]);
      setMessage(`收藏失败：${err instanceof Error ? err.message : '请重试'}`);
    } finally { setSaving(false); }
  }

  /** 收藏成功后的快捷评估入口：显式点击才提交，进度在收藏跟踪查看 */
  async function quickEvaluate(codes: string[]) {
    if (!codes.length) return;
    setQuickPending(true); setQuickNotice('');
    try {
      await dividendApi.analyzeValuation(codes);
      setQuickNotice(`已提交 ${codes.length} 只挡位评估，前往收藏跟踪查看进度`);
    } catch (err) {
      setQuickNotice(err instanceof Error ? `提交评估失败：${err.message}` : '提交评估失败，请重试');
    } finally { setQuickPending(false); }
  }

  const eligibleCodes = result?.items.filter(item => item.status === 'eligible').map(item => item.stock.code) || [];
  const { priceMap } = useRealtimePrices(eligibleCodes);
  const activeView = view === 'insufficient_data' && result?.counts.insufficient_data === 0 ? 'eligible' : view;
  const rows = result?.items.filter(item => item.status === activeView) || [];
  const valid = isScreeningValid(conditions);

  const selectCode = (code: string) => setSelected(prev => { const next = new Set(prev); if (next.has(code)) next.delete(code); else next.add(code); return next; });
  // 未符合/待补视图多一列「原因」；符合条件视图为 8 列
  const showReason = activeView !== 'eligible';
  // 表头：把每个筛选条件的实际值都列出来，方便对照判定
  const tableHeaders: [string, string][] = [
    ['股票', ''],
    ['基本面操作', ''],
    ['五维评级', ''],
    ['三年股息率', ''],
    ['近三年平均ROE', ''],
    ['最近年度ROE', ''],
    ['3年CAGR', ''],
    ['当前股息率（TTM）', ''],
    ['最新季扣非同比', ''],
    ...(showReason ? [['原因', '']] as [string, string][] : []),
    ['收藏', ''],
  ];
  // 评级弹框与详情弹框互斥：开一个先关另一个
  const openDetail = (item: ScreeningItem) => { setQualityModalCode(null); setDetailItem(item); };
  const openQuality = (code: string) => { setDetailItem(null); setQualityModalCode(code); };

  return <section aria-label="选股关注" className="space-y-4">
    <form onSubmit={event => { event.preventDefault(); }} className="rounded-xl border border-rule bg-paper-card p-5">
      <h2 className="text-lg font-semibold text-ink">选出值得持续关注的公司</h2>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        {([['min_yield', '近三年平均股息率 ≥', '0'], ['min_roe_avg_3y', '近三年平均 ROE ≥', '0'], ['min_roe', '最近年度 ROE ≥', '0'], ['max_quarter_profit_decline_pct', '单季扣非利润最大降幅', '0.1'], ['min_cagr_3y', '扣非净利润3年复合增长率 ≥', '-100']] as const).map(([key, label, min]) => <label key={key} className="text-sm text-ink">
          <span className="block mb-1">{label}</span>
          <input aria-label={label} type="number" min={min} max="100" step="0.1" required value={Number.isNaN(conditions[key]) ? '' : conditions[key]} onChange={event => changeConditions({ ...conditions, [key]: event.target.value === '' ? NaN : Number(event.target.value) })} className="w-24 rounded border border-rule-strong bg-paper px-3 py-2" /> %
        </label>)}
        <label className="text-sm text-ink"><span className="block mb-1">交易所</span><select aria-label="选股交易所" value={conditions.exchange || ''} onChange={event => changeConditions({ ...conditions, exchange: event.target.value || undefined })} className="rounded border border-rule-strong bg-paper px-3 py-2"><option value="">全部</option><option>沪市主板</option><option>深市主板</option></select></label>
        <button type="button" className={buttonClass} disabled={loading || saving} onClick={() => changeConditions({ ...DEFAULT_SCREENING })}>恢复默认</button>
        {loading && <span className="text-xs text-ink-muted self-end pb-2.5">筛选中…</span>}
      </div>
      <p className="mt-3 text-xs text-ink-muted">固定条件：近三年每年分红、最近年度扣非净利润 &gt; 0 且年度同比 ≥ 0、单季扣非同比不连续两季为负；单季降幅超过所设阈值时排除。</p>
    </form>
    {error && <p role="alert" className="text-red-600">{error}<button className={`${buttonClass} ml-3`} onClick={() => void query(conditions)} disabled={!valid}>重试筛选</button></p>}
    {result && <>
      <p className="text-sm text-ink-muted">已采集股票池 {result.total} 只 · 分红年度 {result.dividend_years.join(' / ')} · 分红数据更新 <span title={result.last_updated ?? undefined}>{formatTimestamp(result.last_updated)}</span> · 财务更新 <span title={result.financial_last_updated ?? undefined}>{formatTimestamp(result.financial_last_updated)}</span>（报告期见各行）</p>
      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(statusNames) as ScreeningStatus[]).filter(status => status !== 'insufficient_data' || result.counts[status] > 0).map(status => <button key={status} className={`${buttonClass} ${activeView === status ? 'bg-paper-deep border-accent' : ''}`} onClick={() => setView(status)}>{statusNames[status]} {result.counts[status]}</button>)}
        <button className={`${buttonClass} md:ml-auto`} disabled={saving || selected.size === 0} onClick={() => void save([...selected])}>收藏所选 ({selected.size})</button>
        <button className={buttonClass} disabled={saving || eligibleCodes.length === 0} onClick={() => void save(eligibleCodes)}>{saving ? '收藏中…' : '收藏全部符合条件'}</button>
        <div className="screening-quality-actions flex items-center gap-2">
          <QualityQueuePanel view={queueView} onCancel={cancelQueueItem} onMove={moveQueueItem} />
          <QualityReaderEntry sourceQuery={sourceQuery} />
        </div>
      </div>
      {qualityPollError && <p role="status" className="text-sm text-amber-700">评级进度查询失败，任务不受影响，自动重试中…</p>}
      {qualityMessage && <p role="status" className="text-sm text-ink">
        {qualityMessage}
        {qualityJob && qualityJob.failed_codes.length > 0 && qualityJob.status !== 'queued' && qualityJob.status !== 'running' && <button className={`${buttonClass} ml-2`} onClick={() => void analyze(qualityJob.failed_codes)}>重试失败 {qualityJob.failed_codes.length} 只</button>}
      </p>}
      {message && <p role="status" className="text-sm text-ink">{message}{failedCodes.length > 0 && <button className={`${buttonClass} ml-2`} disabled={saving} onClick={() => void save(failedCodes)}>重试失败项</button>}
        {lastAdded.length > 0 && <button className={`${buttonClass} ml-2`} disabled={quickPending || !qualityConfigured} title={qualityConfigured ? '用四挡位估值评估这些新收藏（约几分钟）' : '自动评估暂未启用（后端未完成配置）'} onClick={() => void quickEvaluate(lastAdded)}>{quickPending ? '提交中…' : `评估挡位 (${lastAdded.length})`}</button>}
        {quickNotice && <span className="ml-3 text-ink-muted">{quickNotice}</span>}
      </p>}
      {activeView === 'insufficient_data' && <p className="text-sm text-ink-muted">缺少必需数据的股票暂不入选，通过「数据更新」刷新财务指标后重新查询。</p>}
      <div className="overflow-x-auto rounded-xl border border-rule bg-paper-card">
        <table className="w-full text-sm text-ink whitespace-nowrap"><thead className="bg-paper-deep text-left"><tr>
          <th className="p-3"><input aria-label="勾选全部候选" type="checkbox" disabled={activeView !== 'eligible' || eligibleCodes.length === 0 || saving} checked={eligibleCodes.length > 0 && eligibleCodes.every(code => selected.has(code))} onChange={event => setSelected(new Set(event.target.checked ? eligibleCodes : []))} /></th>
          {tableHeaders.map(([label, hint]) => <th key={label} className="p-3 font-medium" title={hint || undefined}>{label}</th>)}
        </tr></thead><tbody>
          {rows.map(item => {
            const { stock, status, reasons, warnings } = item;
            const score = qualityScores[stock.code];
            return <tr key={stock.code} className="border-t border-rule cursor-pointer hover:bg-paper-tint" onClick={() => openDetail(item)}>
              <td className="p-3" onClick={event => event.stopPropagation()}><input aria-label={`勾选 ${stock.name}`} type="checkbox" disabled={status !== 'eligible' || saving} checked={selected.has(stock.code)} onChange={() => selectCode(stock.code)} /></td>
              <td className="p-3">
                <button className="text-left font-medium text-ink hover:text-accent-hover hover:underline" onClick={event => { event.stopPropagation(); openDetail(item); }}>
                  {stock.name}
                  <span className="block text-xs font-normal text-ink-muted">{stock.code} · {stock.sw_level1 || '—'}</span>
                </button>
              </td>
              <td className="p-3" onClick={event => event.stopPropagation()}>
                {(() => {
                  const live = qualityPerCode[stock.code];
                  if (isQualityPending(live)) {
                    const label = live?.state === 'queued' ? '排队中…' : live?.state === 'cancelling' ? '取消中…' : '评级中…';
                    return <span className="text-xs text-ink-muted animate-pulse" title="评级任务进行中，完成后自动刷新">{label}</span>;
                  }
                  if (live?.state === 'failed') {
                    return <span className="inline-flex items-center gap-2">
                      <span className="text-xs text-red-700" title={live.error || '评级失败'}>失败</span>
                      <button className={buttonClass} disabled={saving || !qualityConfigured} title={live.error || '重新发起评级'} onClick={() => void analyze([stock.code])}>重试</button>
                      <SessionDownloadButton runId={live.run_id} download={dividendApi.downloadQualitySession} />
                    </span>;
                  }
                  return status !== 'eligible'
                    ? <span className="text-ink-muted">待分析</span>
                    : score
                      ? <button className={buttonClass} disabled={pending(stock.code) || saving || !qualityConfigured} title={pending(stock.code) ? '评级任务进行中，完成后自动刷新' : qualityConfigured ? '用当前数据重新评级' : '自动评级暂未启用（后端未完成配置）'} onClick={() => void analyze([stock.code])}>重评</button>
                      : <button className={buttonClass} disabled={pending(stock.code) || saving || !qualityConfigured} title={pending(stock.code) ? '评级任务进行中，完成后自动刷新' : qualityConfigured ? '对这只股票调用 AI 五维基本面评级（约几分钟）' : '自动评级暂未启用（后端未完成配置）'} onClick={() => void analyze([stock.code])}>分析</button>;
                })()}
              </td>
              <td className="p-3" onClick={event => event.stopPropagation()}>
                {score ? <span className="inline-flex items-start gap-2">
                  <button className="inline-grid grid-cols-3 gap-x-3 gap-y-0.5 text-left underline-offset-4 hover:underline" aria-label={`查看${stock.name}的评级报告`} title={`五维评分（各 1–5 分）：${QUALITY_DIMENSION_ORDER.map(key => `${QUALITY_DIMENSION_LABELS[key]} ${score.dimensions[key] ?? '未评分'}`).join(' / ')}；Skill ${score.skill_version ? `v${score.skill_version}` : '版本未知'}；点击查看详情`} onClick={() => openQuality(stock.code)}>
                    {QUALITY_DIMENSION_ORDER.map(key => <span key={key} className="flex items-baseline gap-1">
                      <span className="text-xs text-ink-muted">{QUALITY_DIMENSION_LABELS[key]}</span>
                      <span className="font-mono text-sm font-medium tabular-nums text-ink">{score.dimensions[key] ?? '—'}</span>
                    </span>)}
                  </button>
                  {currentSkillVersion && score.skill_version !== currentSkillVersion && <span className="text-xs text-amber-700" title={`当前已部署 Skill v${currentSkillVersion}，建议重新分析`}>需重评</span>}
                </span> : <span className="text-ink-muted">—</span>}
              </td>
              <td className="p-3 font-mono tabular-nums">{pct(stock.avg_yield_3y)}</td>
              <td className="p-3 font-mono tabular-nums">{pct(stock.roe_avg_3y)}</td>
              <td className="p-3 font-mono tabular-nums">{pct(stock.roe)}</td>
              <td className="p-3 font-mono tabular-nums">
                {stock.net_profit_cagr_3y == null || !Number.isFinite(stock.net_profit_cagr_3y)
                  ? <span className="text-ink-muted" title="近三年有亏损或数据不足，算不出复合增长率">待补</span>
                  : <span className={stock.net_profit_cagr_3y > 0 ? 'text-up' : stock.net_profit_cagr_3y < 0 ? 'text-down' : ''}>{stock.net_profit_cagr_3y.toFixed(2)}%</span>}
              </td>
              <td className="p-3 font-mono tabular-nums">{pct(priceMap.get(stock.code)?.yield_ttm)}</td>
              <td className="p-3">
                <span className={`font-mono tabular-nums ${isDeclining(stock.latest_quarter_yoy_pct) ? 'font-medium text-amber-700' : ''}`}>{pct(stock.latest_quarter_yoy_pct)}</span>
                <span className="block text-xs text-ink-muted">{stock.latest_quarter_label}</span>
              </td>
              {showReason && <td className="p-3 whitespace-normal max-w-sm">
                {reasons.join('；') || '—'}
                {warnings.length > 0 && <span className="block text-amber-700">{warnings.join('；')}</span>}
              </td>}
              <td className="p-3" onClick={event => event.stopPropagation()}>
                {watchlist.has(stock.code)
                  ? <span className="text-ink-muted">已收藏</span>
                  : status === 'eligible'
                    ? <button className={buttonClass} disabled={saving} onClick={() => void save([stock.code])}>加入收藏</button>
                    : <span className="text-ink-muted">—</span>}
              </td>
            </tr>;
          })}
          {rows.length === 0 && <tr><td colSpan={showReason ? 12 : 11} className="p-10 text-center text-ink-muted">{activeView === 'eligible' ? '暂无符合条件的股票，可以调整条件或补充数据。' : '暂无股票'}</td></tr>}
        </tbody></table>
      </div>
    </>}
    <ScreeningStockDetailModal
      item={detailItem}
      price={detailItem ? priceMap.get(detailItem.stock.code) : undefined}
      dataDate={result?.financial_last_updated ?? null}
      onClose={() => setDetailItem(null)}
    />
    <QualityReportModal
      currentSkillVersion={currentSkillVersion}
      score={qualityModalCode ? qualityScores[qualityModalCode] ?? null : null}
      onClose={() => setQualityModalCode(null)}
      onReanalyze={code => void analyze([code])}
      progress={qualityJob ? { processed: qualityJob.processed, total: qualityJob.total } : null}
      reanalyzePending={qualityModalCode ? pending(qualityModalCode) : false}
      reanalyzeDisabled={!qualityConfigured}
    />
  </section>;
}
