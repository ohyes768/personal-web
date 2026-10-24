/**
 * ScreeningStockDetailModal — 选股关注的个股详情弹层
 *
 * 六块结构：状态与提示 / 股息率 / 盈利质量 / 买点参考 / 筹码（+ 头部条）。
 * 行内已有的字段直接渲染（打开即有内容），需要额外接口的块在打开后补拉，
 * 每块独立降级：单个接口失败只让所在块显示「加载失败」，不阻塞其他块。
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import { dividendApi } from '@/lib/api';
import type { ScreeningItem } from '@/lib/screening';
import type { BoardInfo, DividendHistoryItem, DividendStock, M120Stock, PriceItem } from '@/lib/types';
import { Modal } from './shared-ui/Modal';

export interface ScreeningStockDetailModalProps {
  /** 详情对象；null 表示关闭 */
  item: ScreeningItem | null;
  /** 列表同源的现价数据；缺失时组件自行补拉 */
  price?: PriceItem;
  /** 数据日期（财务数据更新时间） */
  dataDate?: string | null;
  onClose: () => void;
}

const BOARD_CACHE_PREFIX = 'dividend-screen-board-info-';
const BOARD_CACHE_DURATION = 24 * 60 * 60 * 1000;

const pct = (value?: number | null) => value == null || !Number.isFinite(value) ? '待补' : `${value.toFixed(2)}%`;
const num = (value?: number | null, digits = 2) => value == null || !Number.isFinite(value) ? '待补' : value.toFixed(digits);
const isDeclining = (value?: number | null) => value != null && Number.isFinite(value) && value < 0;

const statusNames: Record<ScreeningItem['status'], string> = { eligible: '符合条件', excluded: '未符合', insufficient_data: '待补数据' };

function readBoardCache(code: string): BoardInfo | null {
  try {
    const raw = localStorage.getItem(`${BOARD_CACHE_PREFIX}${code}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BoardInfo & { timestamp?: number };
    if (!parsed.timestamp || Date.now() - parsed.timestamp > BOARD_CACHE_DURATION) {
      localStorage.removeItem(`${BOARD_CACHE_PREFIX}${code}`);
      return null;
    }
    return { code: parsed.code, name: parsed.name, concept_board: parsed.concept_board, industry_board: parsed.industry_board };
  } catch {
    return null;
  }
}

function writeBoardCache(info: BoardInfo) {
  try {
    localStorage.setItem(`${BOARD_CACHE_PREFIX}${info.code}`, JSON.stringify({ ...info, timestamp: Date.now() }));
  } catch { /* 缓存失败不影响展示 */ }
}

/** 小块标题 */
function Block({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return <section className="rounded-lg border border-rule bg-paper-card p-4">
    <h3 className="mb-3 text-sm font-semibold text-ink">
      {title}
      {hint && <span className="ml-2 text-xs font-normal text-ink-muted">{hint}</span>}
    </h3>
    {children}
  </section>;
}

/** 键值对（数据密、控件疏） */
function Kpis({ items, columns = 3 }: { items: { label: string; value: string; sub?: string; tone?: 'warn' | 'pos' | 'down' }[]; columns?: number }) {
  return <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
    {items.map(item => <div key={item.label} className="min-w-0">
      <div className="text-xs text-ink-muted">{item.label}</div>
      <div className={`font-mono text-lg font-semibold tabular-nums ${item.tone === 'warn' ? 'text-amber-700' : item.tone === 'pos' ? 'text-emerald-700' : item.tone === 'down' ? 'text-red-700' : 'text-ink'}`}>{item.value}</div>
      {item.sub && <div className="text-xs text-ink-soft">{item.sub}</div>}
    </div>)}
  </div>;
}

export function ScreeningStockDetailModal({ item, price, dataDate, onClose }: ScreeningStockDetailModalProps) {
  const [history, setHistory] = useState<DividendHistoryItem[] | null>(null);
  const [historyError, setHistoryError] = useState('');
  const [board, setBoard] = useState<BoardInfo | null>(null);
  const [boardError, setBoardError] = useState('');
  const [technical, setTechnical] = useState<M120Stock | null>(null);
  const [deviation, setDeviation] = useState<number | null>(null);
  const [technicalError, setTechnicalError] = useState('');
  const [ownPrice, setOwnPrice] = useState<PriceItem | null>(null);
  const [priceError, setPriceError] = useState('');

  const code = item?.stock.code ?? null;

  // 板块信息：缓存优先，缓存缺失再拉
  useEffect(() => {
    if (!code) return;
    setBoardError('');
    const cached = readBoardCache(code);
    if (cached) { setBoard(cached); return; }
    let cancelled = false;
    dividendApi.getBoardInfo({ code })
      .then(response => {
        if (cancelled) return;
        const info = response.items?.[0] ?? null;
        setBoard(info);
        if (info) writeBoardCache(info);
      })
      .catch(() => { if (!cancelled) setBoardError('加载失败'); });
    return () => { cancelled = true; };
  }, [code]);

  // 分红明细
  useEffect(() => {
    if (!code) return;
    setHistoryError('');
    let cancelled = false;
    dividendApi.getStockDetail(code)
      .then(response => { if (!cancelled) setHistory(response.data?.dividend_history ?? null); })
      .catch(() => { if (!cancelled) setHistoryError('加载失败'); });
    return () => { cancelled = true; };
  }, [code]);

  // M120 与偏离度
  useEffect(() => {
    if (!code) return;
    setTechnicalError('');
    let cancelled = false;
    dividendApi.getM120Data()
      .then(async response => {
        if (cancelled) return;
        const found = response.items?.find(item => item.code === code) ?? null;
        setTechnical(found);
        if (!found || found.m120 == null) return;
        const realtime = await dividendApi.getRealtimePrice({ code, m120: found.m120 });
        if (!cancelled) setDeviation(realtime.deviation ?? null);
      })
      .catch(() => { if (!cancelled) setTechnicalError('加载失败'); });
    return () => { cancelled = true; };
  }, [code]);

  // 现价：列表没拉到的（未符合/待补行）在此补拉
  useEffect(() => {
    if (!code || price) return;
    setPriceError('');
    let cancelled = false;
    dividendApi.getPrices([code])
      .then(response => { if (!cancelled) setOwnPrice(response.items?.find(item => item.code === code) ?? null); })
      .catch(() => { if (!cancelled) setPriceError('加载失败'); });
    return () => { cancelled = true; };
  }, [code, price]);

  const handleClose = useCallback(() => onClose(), [onClose]);

  if (!item) return null;

  const { stock, status, reasons, warnings } = item;
  const currentPrice = price ?? ownPrice;
  const swChain = [stock.sw_level1, stock.sw_level2, stock.sw_level3].filter((value): value is string => !!value);
  const conceptBoards = (stock.concept_board || board?.concept_board || '').split(/[,;]+/).map(value => value.trim()).filter(Boolean);
  const industryBoards = (board?.industry_board || '').split(/[,;]+/).map(value => value.trim()).filter(Boolean);
  const years = [
    { year: 2025, dividend: stock.dividend_2025, count: stock.dividend_count_2025, avg: stock.avg_price_2025, yield: stock.yield_2025 },
    { year: 2024, dividend: stock.dividend_2024, count: stock.dividend_count_2024, avg: stock.avg_price_2024, yield: stock.yield_2024 },
    { year: 2023, dividend: stock.dividend_2023, count: stock.dividend_count_2023, avg: stock.avg_price_2023, yield: stock.yield_2023 },
  ];
  const roeHistory = (stock.roe_history ?? []).filter(entry => entry.value != null && Number.isFinite(entry.value));
  const roeMax = roeHistory.reduce((max, entry) => Math.max(max, entry.value ?? 0), 0);
  const dividendRows = (history ?? stock.dividend_history ?? []).slice().sort((a, b) => a.ex_date.localeCompare(b.ex_date)).reverse();
  const yieldGap = stock.avg_yield_3y != null && currentPrice?.yield_ttm != null ? currentPrice.yield_ttm - stock.avg_yield_3y : null;
  const yearYield = (year: number) => stock[`yield_${year}` as keyof DividendStock] as number | null | undefined;

  return <Modal isOpen={!!item} onClose={handleClose} title={`${stock.name}（${stock.code}）`} size="xl">
    <div className="space-y-4">
      {/* 头部条 */}
      <div className="rounded-lg border border-rule bg-paper-card p-4">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-lg font-semibold text-ink">{stock.name}</span>
          <span className="font-mono text-sm text-ink-muted">{stock.code}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
          <span>申万行业：{swChain.length ? swChain.join(' › ') : '待补'}</span>
          {industryBoards.length > 0 && <span>行业板块：{industryBoards.join('、')}</span>}
          {conceptBoards.length > 0 && <span>概念板块：{conceptBoards.join('、')}</span>}
          <span>来源指数：{stock.source_index || '待补'}</span>
          <span>数据日期：{dataDate || '待补'}</span>
          {boardError && <span className="text-amber-700">板块加载失败</span>}
        </div>
      </div>

      {/* 状态与提示 */}
      <Block title="筛选状态" hint="reason = 失败事实，warning = 单季下滑">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className={`rounded-full border px-2 py-0.5 text-xs ${status === 'eligible' ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : status === 'excluded' ? 'border-amber-200 bg-amber-50 text-amber-700' : 'border-rule-strong bg-paper-deep text-ink-muted'}`}>{statusNames[status]}</span>
          {warnings.map(warning => <span key={warning} className="text-amber-700">{warning}</span>)}
        </div>
        {reasons.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm text-ink">
          {reasons.map(reason => <li key={reason}>{reason}</li>)}
        </ul>}
        {status === 'eligible' && reasons.length === 0 && warnings.length === 0 && <p className="mt-2 text-sm text-ink-muted">全部筛选条件通过。</p>}
      </Block>

      {/* 股息率 */}
      <Block title="股息率" hint="分红窗口固定 2023–2025">
        <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-1">
          <div><div className="text-xs text-ink-muted">三年均值</div><div className="font-mono text-xl font-semibold tabular-nums text-ink">{pct(stock.avg_yield_3y)}</div></div>
          <div className="pb-1 text-ink-soft">→</div>
          <div><div className="text-xs text-ink-muted">当前股息率 TTM</div><div className={`font-mono text-xl font-semibold tabular-nums ${currentPrice?.yield_ttm == null ? 'text-ink-muted' : 'text-emerald-700'}`}>{pct(currentPrice?.yield_ttm)}</div></div>
          <div className="pb-1 text-ink-soft">=</div>
          <div><div className="text-xs text-ink-muted">当前相对三年均值</div><div className={`font-mono text-xl font-semibold tabular-nums ${yieldGap == null ? 'text-ink-muted' : yieldGap >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>{yieldGap == null ? '待补' : `${yieldGap >= 0 ? '+' : '−'}${Math.abs(yieldGap).toFixed(2)} pct`}</div></div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-ink">
            <thead className="bg-paper-deep text-left"><tr>
              <th className="p-2 font-medium">年度</th>
              <th className="p-2 font-medium">每股分红</th>
              <th className="p-2 font-medium">分红次数</th>
              <th className="p-2 font-medium">年度均价</th>
              <th className="p-2 font-medium">年度股息率</th>
            </tr></thead>
            <tbody>
              {years.map(entry => <tr key={entry.year} className="border-t border-rule">
                <td className="p-2 font-mono">{entry.year}</td>
                <td className="p-2 font-mono tabular-nums">{entry.dividend == null ? '待补' : `${entry.dividend.toFixed(3)} 元`}</td>
                <td className="p-2 font-mono tabular-nums">{entry.count == null ? '待补' : entry.count}</td>
                <td className="p-2 font-mono tabular-nums">{entry.avg == null ? '待补' : `${entry.avg.toFixed(2)} 元`}</td>
                <td className="p-2 font-mono tabular-nums text-emerald-700">{pct(entry.yield)}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
        <div className="mt-4">
          <div className="mb-1 text-xs text-ink-muted">分红明细{historyError && <span className="ml-2 text-amber-700">{historyError}</span>}</div>
          {dividendRows.length === 0
            ? <p className="text-sm text-ink-muted">{historyError ? '分红明细加载失败。' : '暂无分红明细。'}</p>
            : <div className="overflow-x-auto">
              <table className="w-full text-sm text-ink">
                <thead className="bg-paper-deep text-left"><tr>
                  <th className="p-2 font-medium">除权除息日</th>
                  <th className="p-2 font-medium">财年</th>
                  <th className="p-2 font-medium">派息（元/股）</th>
                  <th className="p-2 font-medium">年度股息率</th>
                </tr></thead>
                <tbody>
                  {dividendRows.map(row => <tr key={`${row.ex_date}-${row.ratio}`} className="border-t border-rule">
                    <td className="p-2 font-mono tabular-nums">{row.ex_date}</td>
                    <td className="p-2 font-mono tabular-nums">{row.fiscal_year}</td>
                    <td className="p-2 font-mono tabular-nums">{row.ratio.toFixed(4)}</td>
                    <td className="p-2 font-mono tabular-nums">{pct(yearYield(row.fiscal_year))}</td>
                  </tr>)}
                </tbody>
              </table>
            </div>}
        </div>
      </Block>

      {/* 盈利质量 */}
      <Block title="盈利质量" hint="年度口径为最近 12-31 累计报表">
        <div className="mb-4">
          <div className="mb-1 text-xs text-ink-muted">ROE 历史</div>
          {roeHistory.length === 0
            ? <p className="text-sm text-ink-muted">待补</p>
            : <div className="flex items-end gap-4">
              {roeHistory.map(entry => <div key={entry.year} className="flex flex-col items-center">
                <div className="text-xs font-mono tabular-nums text-ink">{pct(entry.value)}</div>
                <div className="w-8 rounded-t bg-emerald-600/70" style={{ height: `${Math.max(4, Math.round((entry.value ?? 0) / (roeMax || 1) * 56))}px` }} />
                <div className="mt-1 font-mono text-xs text-ink-soft">{entry.year}</div>
              </div>)}
              <div className="pb-5 text-xs text-ink-muted">近三年平均 ROE <span className="font-mono tabular-nums text-ink">{pct(stock.roe_avg_3y)}</span></div>
            </div>}
        </div>
        <Kpis items={[
          { label: '年度扣非净利润', value: stock.annual_net_profit_ex_non_recurring == null ? '待补' : `${(stock.annual_net_profit_ex_non_recurring / 1e8).toFixed(2)} 亿`, sub: stock.annual_profit_year ? `${stock.annual_profit_year} 年报` : '年度待补' },
          { label: '年度扣非同比', value: pct(stock.net_profit_ex_non_recurring_yoy), tone: isDeclining(stock.net_profit_ex_non_recurring_yoy) ? 'down' : undefined },
          { label: '3 年 CAGR', value: pct(stock.net_profit_cagr_3y) },
          { label: 'EPS', value: stock.eps == null ? '待补' : `${stock.eps.toFixed(2)} 元`, sub: stock.eps_year ? `${stock.eps_year} 年报` : undefined },
          { label: '分红比例', value: pct(stock.payout_ratio) },
        ]} />
        <div className="mt-4 border-t border-rule pt-3">
          <Kpis columns={2} items={[
            { label: `上季 ${stock.previous_quarter_label ?? ''}`, value: pct(stock.previous_quarter_yoy_pct), tone: isDeclining(stock.previous_quarter_yoy_pct) ? 'warn' : undefined },
            { label: `最新季 ${stock.latest_quarter_label ?? ''}`, value: pct(stock.latest_quarter_yoy_pct), tone: isDeclining(stock.latest_quarter_yoy_pct) ? 'warn' : undefined },
          ]} />
        </div>
      </Block>

      {/* 买点参考 */}
      <Block title="买点参考" hint="现价/PE/PB 取列表同源数据，M120 与偏离度按需补拉">
        <Kpis items={[
          { label: '现价', value: currentPrice?.close == null ? '待补' : `${currentPrice.close.toFixed(2)} 元` },
          { label: 'PE（静态）', value: num(currentPrice?.pe) },
          { label: 'PB', value: num(currentPrice?.pb) },
          { label: 'M120', value: technical?.m120 == null ? '待补' : technical.m120.toFixed(2) },
          { label: '偏离度', value: pct(deviation ?? technical?.deviation ?? null), tone: (deviation ?? technical?.deviation ?? 0) > 0 ? 'warn' : undefined },
          { label: '2025 最高', value: stock.high_price_2025 == null ? '待补' : stock.high_price_2025.toFixed(2), sub: stock.high_change_pct_2025 == null ? undefined : `+${stock.high_change_pct_2025.toFixed(2)}%`, tone: stock.high_change_pct_2025 == null ? undefined : 'pos' },
          { label: '2025 最低', value: stock.low_price_2025 == null ? '待补' : stock.low_price_2025.toFixed(2), sub: stock.low_change_pct_2025 == null ? undefined : `−${Math.abs(stock.low_change_pct_2025).toFixed(2)}%`, tone: stock.low_change_pct_2025 == null ? undefined : 'down' },
        ]} columns={4} />
        {(technicalError || priceError) && <p className="mt-2 text-xs text-amber-700">{technicalError ? 'M120/偏离度加载失败' : ''}{technicalError && priceError ? '；' : ''}{priceError ? '现价加载失败' : ''}</p>}
      </Block>

      {/* 筹码 */}
      <Block title="筹码">
        <Kpis items={[
          { label: '股东户数', value: stock.shareholder_count == null ? '待补' : stock.shareholder_count.toLocaleString('zh-CN') },
          { label: '户数增幅', value: pct(stock.shareholder_change_pct), tone: isDeclining(stock.shareholder_change_pct) ? 'pos' : undefined },
          { label: '人均持股', value: stock.per_share_holding == null ? '待补' : stock.per_share_holding.toLocaleString('zh-CN') },
        ]} />
      </Block>

      <p className="text-xs text-ink-soft">缺数据字段显示「待补」，与列表口径一致；单个接口失败只影响所在块，不阻塞弹层打开。</p>
    </div>
  </Modal>;
}
