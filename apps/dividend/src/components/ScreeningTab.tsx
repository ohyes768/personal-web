'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRealtimePrices } from '@/lib/hooks/useRealtimePrices';
import { dividendApi } from '@/lib/api';
import { DEFAULT_SCREENING, type ScreeningConditions, type ScreeningResponse, type ScreeningStatus } from '@/lib/screening';
import type { UseWatchlistResult } from '@/lib/hooks/useWatchlist';

const STORAGE_KEY = 'dividend-screening-conditions-v1';
const pct = (value?: number | null) => value == null ? '待补' : `${value.toFixed(2)}%`;
const statusNames: Record<ScreeningStatus, string> = { eligible: '符合条件', excluded: '未符合', insufficient_data: '待补数据' };
const buttonClass = 'rounded border border-rule-strong px-3 py-2 text-sm text-ink hover:border-accent disabled:opacity-40';

export function ScreeningTab({ watchlist }: { watchlist: UseWatchlistResult }) {
  const [conditions, setConditions] = useState<ScreeningConditions>(DEFAULT_SCREENING);
  const [result, setResult] = useState<ScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<ScreeningStatus>('eligible');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [failedCodes, setFailedCodes] = useState<string[]>([]);
  const requestId = useRef(0);
  const query = useCallback(async (next: ScreeningConditions) => {
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
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (stored && ['min_yield', 'min_roe', 'min_roe_avg_3y'].every(key => typeof stored[key] === 'number' && Number.isFinite(stored[key]) && stored[key] >= 0 && stored[key] <= 100)) {
        next = { min_yield: stored.min_yield, min_roe: stored.min_roe, min_roe_avg_3y: stored.min_roe_avg_3y,
          exchange: ['沪市主板', '深市主板'].includes(stored.exchange) ? stored.exchange : undefined };
      }
    } catch { /* unavailable storage uses defaults */ }
    setConditions(next); void query(next);
    return () => { requestId.current++; };
  }, [query]);

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
  const rows = result?.items.filter(item => item.status === view) || [];
  const valid = [conditions.min_yield, conditions.min_roe, conditions.min_roe_avg_3y].every(value => Number.isFinite(value) && value >= 0 && value <= 100);
  const changed = result && (['min_yield', 'min_roe', 'min_roe_avg_3y'] as const).some(key => result.conditions[key] !== conditions[key]) || !!result && (result.conditions.exchange || '') !== (conditions.exchange || '');
  const selectCode = (code: string) => setSelected(prev => { const next = new Set(prev); if (next.has(code)) next.delete(code); else next.add(code); return next; });

  return <section aria-label="选股关注" className="space-y-4">
    <form onSubmit={event => { event.preventDefault(); if (!valid) return; try { localStorage.setItem(STORAGE_KEY, JSON.stringify(conditions)); } catch {} void query(conditions); }} className="rounded-xl border border-rule bg-paper-card p-5">
      <h2 className="text-lg font-semibold text-ink">选出值得持续关注的公司</h2>
      <p className="mt-1 text-sm text-ink-muted">分红稳定、ROE 达标、年度主业利润不下滑；连续两季扣非同比为负时排除。当前股息率由你人工判断。</p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        {([['min_yield', '近三年平均股息率 ≥'], ['min_roe_avg_3y', '近三年平均 ROE ≥'], ['min_roe', '最近年度 ROE ≥']] as const).map(([key, label]) => <label key={key} className="text-sm text-ink">
          <span className="block mb-1">{label}</span>
          <input aria-label={label} type="number" min="0" max="100" step="0.1" required value={Number.isNaN(conditions[key]) ? '' : conditions[key]} onChange={event => setConditions(prev => ({ ...prev, [key]: event.target.value === '' ? NaN : Number(event.target.value) }))} className="w-24 rounded border border-rule-strong bg-paper px-3 py-2" /> %
        </label>)}
        <label className="text-sm text-ink"><span className="block mb-1">交易所</span><select aria-label="选股交易所" value={conditions.exchange || ''} onChange={event => setConditions(prev => ({ ...prev, exchange: event.target.value || undefined }))} className="rounded border border-rule-strong bg-paper px-3 py-2"><option value="">全部</option><option>沪市主板</option><option>深市主板</option></select></label>
        <button className={`${buttonClass} bg-indigo-600 text-white`} disabled={loading || saving || !valid}>{loading ? '筛选中…' : '查询候选'}</button>
        <button type="button" className={buttonClass} disabled={loading || saving} onClick={() => { const next = { ...DEFAULT_SCREENING }; setConditions(next); try { localStorage.removeItem(STORAGE_KEY); } catch {} void query(next); }}>恢复默认</button>
      </div>
      <p className="mt-3 text-xs text-ink-muted">固定条件：近三年每年分红、年度扣非同比 ≥ 0、不能连续两季单季扣非同比为负。条件在此浏览器保存。</p>
    </form>
    {error && <p role="alert" className="text-red-600">{error}<button className={`${buttonClass} ml-3`} onClick={() => void query(conditions)} disabled={!valid}>重试筛选</button></p>}
    {result && <>
      <p className="text-sm text-ink-muted">已采集股票池 {result.total} 只 · 分红年度 {result.dividend_years.join(' / ')} · 分红数据更新 {result.last_updated || '暂无记录'} · 财务更新 {result.financial_last_updated || '暂无记录'}（报告期见各行）</p>
      {changed && <p className="text-sm text-amber-700">条件已修改，当前仍显示上次查询结果，请点击「查询候选」。</p>}
      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(statusNames) as ScreeningStatus[]).map(status => <button key={status} className={`${buttonClass} ${view === status ? 'bg-paper-deep border-accent' : ''}`} onClick={() => setView(status)}>{statusNames[status]} {result.counts[status]}</button>)}
        <button className={`${buttonClass} md:ml-auto`} disabled={saving || selected.size === 0} onClick={() => void save([...selected])}>收藏所选 ({selected.size})</button>
        <button className={buttonClass} disabled={saving || eligibleCodes.length === 0} onClick={() => void save(eligibleCodes)}>{saving ? '收藏中…' : '收藏全部符合条件'}</button>
      </div>
      {message && <p role="status" className="text-sm text-ink">{message}{failedCodes.length > 0 && <button className={`${buttonClass} ml-2`} disabled={saving} onClick={() => void save(failedCodes)}>重试失败项</button>}</p>}
      {view === 'insufficient_data' && <p className="text-sm text-ink-muted">缺少必需数据的股票暂不入选。请通过「数据更新」刷新财务指标后重新查询。旧数据首次补齐历史字段时，请勾选「强制」刷新。</p>}
      <div className="overflow-x-auto rounded-xl border border-rule bg-paper-card">
        <table className="w-full text-sm text-ink whitespace-nowrap"><thead className="bg-paper-deep text-left"><tr>
          <th className="p-3"><input aria-label="勾选全部候选" type="checkbox" disabled={view !== 'eligible' || eligibleCodes.length === 0 || saving} checked={eligibleCodes.length > 0 && eligibleCodes.every(code => selected.has(code))} onChange={event => setSelected(new Set(event.target.checked ? eligibleCodes : []))} /></th>
          {['股票', '三年股息率', '当前股息率（参考）', '三年平均 ROE', '年度 ROE', '年度扣非同比', '上季扣非同比', '最新季度扣非同比', '入选指标 / 原因', '收藏'].map(label => <th key={label} className="p-3 font-medium">{label}</th>)}
        </tr></thead><tbody>
          {rows.map(({ stock, status, reasons, warnings }) => <tr key={stock.code} className="border-t border-rule">
            <td className="p-3"><input aria-label={`勾选 ${stock.name}`} type="checkbox" disabled={status !== 'eligible' || saving} checked={selected.has(stock.code)} onChange={() => selectCode(stock.code)} /></td>
            <td className="p-3 font-medium">{stock.name}<span className="block text-xs text-ink-muted">{stock.code}</span></td>
            <td className="p-3">{pct(stock.avg_yield_3y)}</td>
            <td className="p-3">{pct(priceMap.get(stock.code)?.yield_ttm)}</td>
            <td className="p-3" title={stock.roe_history?.map(item => `${item.year}: ${pct(item.value)}`).join('；')}>{pct(stock.roe_avg_3y)}</td>
            <td className="p-3">{pct(stock.roe)}<span className="block text-xs text-ink-muted">{stock.roe_year || '年度待补'}</span></td>
            <td className="p-3">{pct(stock.net_profit_ex_non_recurring_yoy)}</td>
            <td className="p-3">{pct(stock.previous_quarter_yoy_pct)}<span className="block text-xs text-ink-muted">{stock.previous_quarter_label}</span></td>
            <td className="p-3">{pct(stock.latest_quarter_yoy_pct)}<span className="block text-xs text-ink-muted">{stock.latest_quarter_label}</span></td>
            <td className="p-3 whitespace-normal min-w-56 max-w-sm">{reasons.join('；') || '分红连续、ROE 达标、年度利润未下降、两季规则通过'}{warnings.length > 0 && <span className="block text-amber-700">{warnings.join('；')}</span>}</td>
            <td className="p-3">{watchlist.has(stock.code) ? '已收藏' : <button className={buttonClass} disabled={saving || status !== 'eligible'} onClick={() => void save([stock.code])}>加入收藏</button>}</td>
          </tr>)}
          {rows.length === 0 && <tr><td colSpan={11} className="p-10 text-center text-ink-muted">{view === 'eligible' ? '暂无符合条件的股票，可以调整条件或补充数据。' : '暂无股票'}</td></tr>}
        </tbody></table>
      </div>
    </>}
  </section>;
}
