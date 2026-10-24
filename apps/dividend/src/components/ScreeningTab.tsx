'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRealtimePrices } from '@/lib/hooks/useRealtimePrices';
import { useQualityAnalysis } from '@/lib/hooks/useQualityAnalysis';
import { dividendApi } from '@/lib/api';
import { DEFAULT_SCREENING, restoreScreeningConditions, type ScreeningConditions, type ScreeningItem, type ScreeningResponse, type ScreeningStatus } from '@/lib/screening';
import type { UseWatchlistResult } from '@/lib/hooks/useWatchlist';
import { QualityReportModal } from './QualityReportModal';
import { ScreeningStockDetailModal } from './ScreeningStockDetailModal';

const STORAGE_KEY = 'dividend-screening-conditions-v1';
const pct = (value?: number | null) => value == null || !Number.isFinite(value) ? '待补' : `${value.toFixed(2)}%`;
const isDeclining = (value?: number | null) => value != null && Number.isFinite(value) && value < 0;
const statusNames: Record<ScreeningStatus, string> = { eligible: '符合条件', excluded: '未符合', insufficient_data: '待补数据' };
const buttonClass = 'rounded border border-rule-strong px-3 py-2 text-sm text-ink hover:border-accent disabled:opacity-40';

export function ScreeningTab({ watchlist, refreshRevision = 0 }: { watchlist: UseWatchlistResult; refreshRevision?: number }) {
  const [conditions, setConditions] = useState<ScreeningConditions>(DEFAULT_SCREENING);
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<ScreeningStatus>('eligible');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [failedCodes, setFailedCodes] = useState<string[]>([]);
  const [qualityModalCode, setQualityModalCode] = useState<string | null>(null);
  const [detailItem, setDetailItem] = useState<ScreeningItem | null>(null);
  const { qualityScores, qualityConfigured, analyzing, qualityJob, qualityMessage, analyze } = useQualityAnalysis();
  const requestId = useRef(0);
  const appliedConditions = useRef(DEFAULT_SCREENING);
  const previousRevision = useRef(refreshRevision);
  const query = useCallback(async (next: ScreeningConditions) => {
    appliedConditions.current = next;
    const id = ++requestId.current;
    setLoading(true); setError(''); setSelected(new Set()); setResult(null); setMessage(''); setFailedCodes([]);
    try {
      const response = await dividendApi.screenStocks(next);
      if (id === requestId.current) setResult(response);
    } catch (err) {
      if (id === requestId.current) setError(err instanceof Error ? err.message : '筛选失败');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let next = { ...DEFAULT_SCREENING };
    try {
      next = restoreScreeningConditions(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null'));
    } catch { /* unavailable storage uses defaults */ }
    setConditions(next); void query(next);
    return () => { requestId.current++; };
  }, [query]);

  useEffect(() => {
    if (previousRevision.current !== refreshRevision) {
      previousRevision.current = refreshRevision;
      void query(appliedConditions.current);
    }
  }, [refreshRevision, query]);

  async function save(codes: string[]) {
    if (!codes.length) return;
    setSaving(true); setMessage(''); setFailedCodes([]);
    try {
      const response = await dividendApi.addFavoritesBatch(codes);
      const failed = response.items.filter(item => item.status === 'failed');
      setFailedCodes(failed.map(item => item.code));
      setMessage(`新增 ${response.items.filter(item => item.status === 'added').length} 只，已收藏 ${response.items.filter(item => item.status === 'already_exists').length} 只，失败 ${failed.length} 只${failed.length ? '：' + failed.map(item => `${item.code} ${item.error || ''}`).join('；') : ''}`);
      setSelected(new Set(failed.map(item => item.code)));
      try { localStorage.setItem('watchlist-sync-tick', String(Date.now())); } catch { /* refresh still works */ }
      await watchlist.refresh();
    } catch (err) {
      setFailedCodes(codes);
      setMessage(`收藏失败：${err instanceof Error ? err.message : '请重试'}`);
    } finally { setSaving(false); }
  }

  const eligibleCodes = result?.items.filter(item => item.status === 'eligible').map(item => item.stock.code) || [];
  const { priceMap } = useRealtimePrices(eligibleCodes);
  const activeView = view === 'insufficient_data' && result?.counts.insufficient_data === 0 ? 'eligible' : view;
  const rows = result?.items.filter(item => item.status === activeView) || [];
  const valid = [conditions.min_yield, conditions.min_roe, conditions.min_roe_avg_3y].every(value => Number.isFinite(value) && value >= 0 && value <= 100) && Number.isFinite(conditions.max_quarter_profit_decline_pct) && conditions.max_quarter_profit_decline_pct > 0 && conditions.max_quarter_profit_decline_pct <= 100;
  const changed = result && (['min_yield', 'min_roe', 'min_roe_avg_3y', 'max_quarter_profit_decline_pct'] as const).some(key => result.conditions[key] !== conditions[key]) || !!result && (result.conditions.exchange || '') !== (conditions.exchange || '');
  const selectCode = (code: string) => setSelected(prev => { const next = new Set(prev); if (next.has(code)) next.delete(code); else next.add(code); return next; });
  // 未符合/待补视图多一列「原因」；符合条件视图为 8 列
  const showReason = activeView !== 'eligible';
  // 评级弹框与详情弹框互斥：开一个先关另一个
  const openDetail = (item: ScreeningItem) => { setQualityModalCode(null); setDetailItem(item); };
  const openQuality = (code: string) => { setDetailItem(null); setQualityModalCode(code); };

  return <section aria-label="选股关注" className="space-y-4">
    <form onSubmit={event => { event.preventDefault(); if (!valid) return; try { localStorage.setItem(STORAGE_KEY, JSON.stringify(conditions)); } catch {} void query(conditions); }} className="rounded-xl border border-rule bg-paper-card p-5">
      <h2 className="text-lg font-semibold text-ink">选出值得持续关注的公司</h2>
      <p className="mt-1 text-sm text-ink-muted">分红稳定、ROE 达标、最近年度扣非净利润为正且同比不下滑；连续两季扣非同比为负或任一季降幅达到所设阈值时排除。当前股息率由你人工判断。</p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        {([['min_yield', '近三年平均股息率 ≥'], ['min_roe_avg_3y', '近三年平均 ROE ≥'], ['min_roe', '最近年度 ROE ≥'], ['max_quarter_profit_decline_pct', '单季扣非利润最大降幅']] as const).map(([key, label]) => <label key={key} className="text-sm text-ink">
          <span className="block mb-1">{label}</span>
          <input aria-label={label} type="number" min={key === 'max_quarter_profit_decline_pct' ? '0.1' : '0'} max="100" step="0.1" required value={Number.isNaN(conditions[key]) ? '' : conditions[key]} onChange={event => setConditions(prev => ({ ...prev, [key]: event.target.value === '' ? NaN : Number(event.target.value) }))} className="w-24 rounded border border-rule-strong bg-paper px-3 py-2" /> %
        </label>)}
        <label className="text-sm text-ink"><span className="block mb-1">交易所</span><select aria-label="选股交易所" value={conditions.exchange || ''} onChange={event => setConditions(prev => ({ ...prev, exchange: event.target.value || undefined }))} className="rounded border border-rule-strong bg-paper px-3 py-2"><option value="">全部</option><option>沪市主板</option><option>深市主板</option></select></label>
        <button className={`${buttonClass} bg-indigo-600 text-white`} disabled={loading || saving || !valid}>{loading ? '筛选中…' : '查询候选'}</button>
        <button type="button" className={buttonClass} disabled={loading || saving} onClick={() => { const next = { ...DEFAULT_SCREENING }; setConditions(next); try { localStorage.removeItem(STORAGE_KEY); } catch {} void query(next); }}>恢复默认</button>
      </div>
      <p className="mt-3 text-xs text-ink-muted">固定条件：近三年每年分红、最近年度扣非净利润 &gt; 0、年度扣非同比 ≥ 0、不能连续两季单季扣非同比为负。单季同比 ≤ −所设降幅时排除。条件在此浏览器保存。</p>
    </form>
    {error && <p role="alert" className="text-red-600">{error}<button className={`${buttonClass} ml-3`} onClick={() => void query(conditions)} disabled={!valid}>重试筛选</button></p>}
    {result && <>
      <p className="text-sm text-ink-muted">已采集股票池 {result.total} 只 · 分红年度 {result.dividend_years.join(' / ')} · 分红数据更新 {result.last_updated || '暂无记录'} · 财务更新 {result.financial_last_updated || '暂无记录'}（报告期见各行）</p>
      {changed && <p className="text-sm text-amber-700">条件已修改，当前仍显示上次查询结果，请点击「查询候选」。</p>}
      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(statusNames) as ScreeningStatus[]).filter(status => status !== 'insufficient_data' || result.counts[status] > 0).map(status => <button key={status} className={`${buttonClass} ${activeView === status ? 'bg-paper-deep border-accent' : ''}`} onClick={() => setView(status)}>{statusNames[status]} {result.counts[status]}</button>)}
        <button className={`${buttonClass} md:ml-auto`} disabled={saving || selected.size === 0} onClick={() => void save([...selected])}>收藏所选 ({selected.size})</button>
        <button className={buttonClass} disabled={saving || eligibleCodes.length === 0} onClick={() => void save(eligibleCodes)}>{saving ? '收藏中…' : '收藏全部符合条件'}</button>
        <button className={`${buttonClass} bg-indigo-600 text-white`} disabled={!qualityConfigured || analyzing || saving || selected.size === 0} title={qualityConfigured ? '对勾选股票调用 AI 五维基本面评级（每只约几分钟）' : 'Hermes 未配置（需 HERMES_BASE_URL 与 HERMES_API_KEY），无法评级'} onClick={() => void analyze([...selected])}>{analyzing ? qualityJob ? `分析中 ${qualityJob.processed}/${qualityJob.total}…` : '提交中…' : `分析基本面 (${selected.size})`}</button>
        {!analyzing && qualityJob && qualityJob.failed_codes.length > 0 && <button className={buttonClass} onClick={() => void analyze(qualityJob.failed_codes)}>重试失败 {qualityJob.failed_codes.length} 只</button>}
      </div>
      {qualityMessage && <p role="status" className="text-sm text-ink">{qualityMessage}</p>}
      {message && <p role="status" className="text-sm text-ink">{message}{failedCodes.length > 0 && <button className={`${buttonClass} ml-2`} disabled={saving} onClick={() => void save(failedCodes)}>重试失败项</button>}</p>}
      {activeView === 'insufficient_data' && <p className="text-sm text-ink-muted">缺少必需数据的股票暂不入选。请通过「数据更新」刷新财务指标后重新查询。旧财务缓存补齐年度扣非净利润金额、年度及历史字段时，请对全量股票勾选「强制」刷新；来源仍缺失的数据继续待补。</p>}
      <div className="overflow-x-auto rounded-xl border border-rule bg-paper-card">
        <table className="w-full text-sm text-ink whitespace-nowrap"><thead className="bg-paper-deep text-left"><tr>
          <th className="p-3"><input aria-label="勾选全部候选" type="checkbox" disabled={activeView !== 'eligible' || eligibleCodes.length === 0 || saving} checked={eligibleCodes.length > 0 && eligibleCodes.every(code => selected.has(code))} onChange={event => setSelected(new Set(event.target.checked ? eligibleCodes : []))} /></th>
          {['股票', '基本面操作', '评级结果', '三年股息率', '当前股息率（TTM）', '最新季扣非同比', ...(showReason ? ['原因'] : []), '收藏'].map(label => <th key={label} className="p-3 font-medium">{label}</th>)}
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
                {status !== 'eligible'
                  ? <span className="text-ink-muted">待分析</span>
                  : score
                    ? <button className={buttonClass} disabled={analyzing || saving || !qualityConfigured} title={qualityConfigured ? '用当前数据重新评级' : 'Hermes 未配置，无法评级'} onClick={() => void analyze([stock.code])}>重评</button>
                    : <button className={buttonClass} disabled={analyzing || saving || !qualityConfigured} title={qualityConfigured ? '对这只股票调用 AI 五维基本面评级（约几分钟）' : 'Hermes 未配置（需 HERMES_BASE_URL 与 HERMES_API_KEY），无法评级'} onClick={() => void analyze([stock.code])}>分析</button>}
              </td>
              <td className="p-3" onClick={event => event.stopPropagation()}>
                {score
                  ? <button className="font-mono tabular-nums text-ink hover:underline" title="查看基本面评级详情" onClick={() => openQuality(stock.code)}>
                      {score.weighted_score.toFixed(1)}
                      {score.boundary && <span className="ml-1 text-xs text-amber-700" title={score.boundary}>⚠️</span>}
                    </button>
                  : <span className="text-ink-muted">-</span>}
              </td>
              <td className="p-3 font-mono tabular-nums">{pct(stock.avg_yield_3y)}</td>
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
          {rows.length === 0 && <tr><td colSpan={showReason ? 9 : 8} className="p-10 text-center text-ink-muted">{activeView === 'eligible' ? '暂无符合条件的股票，可以调整条件或补充数据。' : '暂无股票'}</td></tr>}
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
      score={qualityModalCode ? qualityScores[qualityModalCode] ?? null : null}
      onClose={() => setQualityModalCode(null)}
      onReanalyze={code => void analyze([code])}
      analyzing={analyzing}
      progress={qualityJob ? { processed: qualityJob.processed, total: qualityJob.total } : null}
      reanalyzeDisabled={!qualityConfigured}
    />
  </section>;
}
