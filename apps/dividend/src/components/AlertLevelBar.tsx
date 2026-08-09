/**
 * AlertLevelBar — 单只股票的水平价位条
 *
 * 紧凑布局：
 *   L1 股票头：代码/名 + 距各档 + 现价/涨幅/操作建议
 *   L2 细色条 + 5 点（上价格 / 下 PE·PB）；区名在色条下方对齐五区
 *   点击点：弹出该价位股息率（2025 分红 / 价格）
 */

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { AlertLevels } from '@/lib/types';

export interface AlertLevelBarProps {
  code: string;
  name: string;
  levels: AlertLevels;
  currentPrice: number;
  currentPE?: number | null;
  currentPB?: number | null;
  /** 2025 年每股分红（元），用于计算各价位股息率 */
  dividend2025?: number | null;
  /** 实时股息率 TTM（%），仅现价点展示 */
  yieldTtm?: number | null;
  /** 现价数据拉取时间（ISO 字符串），用于在 L1 行展示"更新于 MM-DD HH:MM" */
  priceUpdatedAt?: string | null;
  onClick?: () => void;
}

type LevelKey = 'heavy_position' | 'add_position' | 'reduce_position' | 'full_exit';
type SegSide = 'heavy' | 'add' | 'hold' | 'reduce' | 'full';
type YieldKey = LevelKey | 'current';

const LEVEL_META: Record<LevelKey, { tag: string; shortLabel: string; color: 'green' | 'yellow' | 'orange' | 'red' }> = {
  heavy_position:  { tag: '重仓', shortLabel: '重仓', color: 'green'  },
  add_position:    { tag: '加仓', shortLabel: '加仓', color: 'yellow' },
  reduce_position: { tag: '减仓', shortLabel: '减仓', color: 'orange' },
  full_exit:       { tag: '全卖', shortLabel: '全卖', color: 'red'    },
};

const SEG_COLORS: Record<SegSide, string> = {
  heavy:  '#5A9472',
  add:    '#C9951F',
  hold:   '#D9D2C2',
  reduce: '#D4893A',
  full:   '#9B2F2F',
};

const SEG_LABELS: Record<SegSide, string> = {
  heavy:  '重仓区',
  add:    '加仓区',
  hold:   '持有区',
  reduce: '减仓区',
  full:   '全卖区',
};

const HIT_META: Record<SegSide | 'inactive', { label: string; cls: string } | null> = {
  heavy:  { label: '可加仓',   cls: 'bg-green-50 text-green-700 border border-green-200' },
  add:    { label: '加仓价位', cls: 'bg-yellow-50 text-yellow-700 border border-yellow-200' },
  reduce: { label: '该减仓',   cls: 'bg-orange-50 text-orange-700 border border-orange-200' },
  full:   { label: '全部清仓', cls: 'bg-red-50 text-red-700 border border-red-200' },
  hold:   { label: '持有观望', cls: 'bg-slate-50 text-slate-600 border border-slate-200' },
  inactive: null,
};

interface PricePoint {
  key: LevelKey;
  price: number;
}

function gapColor(leftKey: LevelKey | null, rightKey: LevelKey | null): SegSide {
  const keyToSeg = (k: LevelKey): Exclude<SegSide, 'hold'> => {
    if (k === 'heavy_position') return 'heavy';
    if (k === 'add_position') return 'add';
    if (k === 'reduce_position') return 'reduce';
    return 'full';
  };
  const isBuy = (k: LevelKey) => k === 'heavy_position' || k === 'add_position';
  const isSell = (k: LevelKey) => k === 'reduce_position' || k === 'full_exit';

  if (!leftKey && rightKey) return keyToSeg(rightKey);
  if (leftKey && !rightKey) return keyToSeg(leftKey);
  if (leftKey && rightKey) {
    if (isBuy(leftKey) && isBuy(rightKey)) return keyToSeg(rightKey);
    if (isSell(leftKey) && isSell(rightKey)) return keyToSeg(leftKey);
    if (isBuy(leftKey) && isSell(rightKey)) return 'hold';
  }
  return 'hold';
}

function hitStatus(levels: AlertLevels, currentPrice: number): SegSide {
  const heavy = levels.heavy_position?.price;
  const add = levels.add_position?.price;
  const reduce = levels.reduce_position?.price;
  const full = levels.full_exit?.price;
  if (heavy && currentPrice <= heavy) return 'heavy';
  if (add && currentPrice <= add) return 'add';
  if (full && currentPrice >= full) return 'full';
  if (reduce && currentPrice >= reduce) return 'reduce';
  return 'hold';
}

function fmtPrice(p: number): string {
  return p.toFixed(2);
}

function fmtPct(p: number): string {
  const sign = p > 0 ? '+' : '';
  return `${sign}${p.toFixed(1)}%`;
}

/** ISO 字符串 → "MM-DD HH:MM"（本地时区），无效入参返回 null */
function fmtPriceUpdatedAt(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const pad = (n: number) => n.toString().padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtPePb(pe?: number | null, pb?: number | null): string | null {
  const parts: string[] = [];
  if (pe != null) parts.push(`PE ${pe.toFixed(1)}`);
  if (pb != null) parts.push(`PB ${pb.toFixed(2)}`);
  return parts.length > 0 ? parts.join(' / ') : null;
}

function calcYieldAtPrice(dividend: number | null | undefined, price: number): number | null {
  if (dividend == null || dividend <= 0 || price <= 0) return null;
  return (dividend / price) * 100;
}

function yieldTone(y: number): string {
  if (y >= 5) return 'text-emerald-700';
  if (y >= 3) return 'text-emerald-600';
  return 'text-ink';
}

function distTone(pct: number, isHit: boolean): { cls: string; suffix: string } {
  if (isHit || Math.abs(pct) < 5) {
    return { cls: 'text-red-600 font-semibold', suffix: ' ✓' };
  }
  if (Math.abs(pct) < 10) {
    return { cls: 'text-yellow-700', suffix: '' };
  }
  return { cls: 'text-ink-muted', suffix: '' };
}

/** 价位过近时上下错层：返回 0=上层 / 1=下层 */
function staggerRows(lefts: number[], minGap = 12): number[] {
  const rows = lefts.map(() => 0);
  for (let i = 1; i < lefts.length; i++) {
    if (Math.abs(lefts[i] - lefts[i - 1]) < minGap) {
      rows[i] = rows[i - 1] === 0 ? 1 : 0;
    }
  }
  return rows;
}

function popoverAlign(leftPct: number): 'left' | 'center' | 'right' {
  if (leftPct >= 78) return 'right';
  if (leftPct <= 22) return 'left';
  return 'center';
}

export function AlertLevelBar({
  code,
  name,
  levels,
  currentPrice,
  currentPE,
  currentPB,
  dividend2025,
  yieldTtm,
  priceUpdatedAt,
  onClick,
}: AlertLevelBarProps) {
  const [openYield, setOpenYield] = useState<YieldKey | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Esc / 点空白关闭股息率浮层
  useEffect(() => {
    if (openYield == null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenYield(null);
    };
    const onPointer = (e: MouseEvent | PointerEvent) => {
      const el = rootRef.current;
      if (!el) return;
      if (e.target instanceof Node && !el.contains(e.target)) {
        setOpenYield(null);
      }
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [openYield]);

  const points: PricePoint[] = useMemo(() => {
    const list: PricePoint[] = [];
    (Object.keys(LEVEL_META) as LevelKey[]).forEach(k => {
      const lv = levels[k];
      if (lv && lv.price > 0) {
        list.push({ key: k, price: lv.price });
      }
    });
    return list;
  }, [levels]);

  if (points.length < 2) {
    return null;
  }

  const minP = Math.min(...points.map(p => p.price));
  const maxP = Math.max(...points.map(p => p.price));
  const range = maxP - minP || 1;
  const pct = (p: number) => Math.max(5, Math.min(95, ((p - minP) / range) * 100));

  const sortedPoints = [...points].sort((a, b) => a.price - b.price);

  const segments: Array<{ side: SegSide; left: number; width: number }> = [];
  if (sortedPoints.length >= 1) {
    segments.push({
      side: gapColor(null, sortedPoints[0].key),
      left: 0,
      width: pct(sortedPoints[0].price),
    });
    for (let i = 0; i < sortedPoints.length - 1; i++) {
      const leftPct = pct(sortedPoints[i].price);
      const rightPct = pct(sortedPoints[i + 1].price);
      const width = rightPct - leftPct;
      if (width <= 0) continue;
      segments.push({
        side: gapColor(sortedPoints[i].key, sortedPoints[i + 1].key),
        left: leftPct,
        width,
      });
    }
    const lastPct = pct(sortedPoints[sortedPoints.length - 1].price);
    const lastWidth = 100 - lastPct;
    if (lastWidth > 0) {
      segments.push({
        side: gapColor(sortedPoints[sortedPoints.length - 1].key, null),
        left: lastPct,
        width: lastWidth,
      });
    }
  }

  const status = hitStatus(levels, currentPrice);
  const badge = HIT_META[status];

  const change = (() => {
    const closest = sortedPoints.reduce((prev, p) =>
      Math.abs(p.price - currentPrice) < Math.abs(prev.price - currentPrice) ? p : prev
    );
    if (closest.price === 0) return null;
    return ((currentPrice - closest.price) / closest.price) * 100;
  })();

  const distances = sortedPoints.map(p => {
    const isHit =
      p.key === 'heavy_position' || p.key === 'add_position'
        ? currentPrice <= p.price
        : currentPrice >= p.price;
    return {
      key: p.key,
      price: p.price,
      pct: p.price > 0 ? ((currentPrice - p.price) / p.price) * 100 : 0,
      isHit,
    };
  });

  const markerLeftPct = Math.max(8, Math.min(92, pct(currentPrice)));

  // 价格标签错层：档位 + 现价一起算，过近则上下错开
  const labelLefts = [
    ...sortedPoints.map(p => Math.max(4, Math.min(96, pct(p.price)))),
    markerLeftPct,
  ];
  const labelRows = staggerRows(labelLefts);
  const levelRows = labelRows.slice(0, sortedPoints.length);
  const currentRow = labelRows[labelRows.length - 1] ?? 0;

  const closeYield = () => setOpenYield(null);

  return (
    <div
      ref={rootRef}
      className={`bg-paper-card border border-rule rounded-lg px-2.5 py-2 ${onClick ? 'cursor-pointer hover:border-rule-strong transition-colors duration-200' : ''}`}
      onClick={() => {
        closeYield();
        onClick?.();
      }}
      data-code={code}
    >
      {/* L1 */}
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <span className="font-semibold text-ink text-sm">{code}</span>
        <span className="text-ink-muted text-xs truncate max-w-[6rem] sm:max-w-none">{name}</span>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-mono">
          {distances.map(d => {
            const meta = LEVEL_META[d.key];
            const tone = distTone(d.pct, d.isHit);
            return (
              <span key={d.key} className={tone.cls}>
                距{meta.shortLabel} {fmtPct(d.pct)}{tone.suffix}
              </span>
            );
          })}
        </div>
        <span className="font-mono font-semibold text-ink text-sm ml-auto tabular-nums">¥{fmtPrice(currentPrice)}</span>
        {change !== null && (
          <span className={`font-mono text-[11px] tabular-nums ${change >= 0 ? 'text-up' : 'text-down'}`}>
            {fmtPct(change)}
          </span>
        )}
        {badge && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap ${badge.cls}`}>
            {badge.label}
          </span>
        )}
        {(() => {
          const updated = fmtPriceUpdatedAt(priceUpdatedAt);
          return updated ? (
            <span
              className="text-[10px] font-mono text-ink-muted whitespace-nowrap"
              title={`现价更新于 ${updated}`}
            >
              更新 {updated}
            </span>
          ) : null;
        })()}
      </div>

      {/* L2：价格 → 细条 → 点/PE·PB → 五区名 */}
      {/* pt 含错层第二行；pb 给 PE/PB + 区名 */}
      <div className="relative pt-7 pb-9">
        <div className="relative h-3.5 bg-paper-deep rounded-full overflow-hidden">
          {segments.map((seg, i) => (
            <div
              key={i}
              className="absolute top-0 bottom-0"
              style={{
                left: `${seg.left}%`,
                width: `${seg.width}%`,
                backgroundColor: SEG_COLORS[seg.side],
              }}
            />
          ))}
        </div>

        {/* 4 档位点 */}
        {sortedPoints.map((p, idx) => {
          const left = Math.max(4, Math.min(96, pct(p.price)));
          const meta = LEVEL_META[p.key];
          const tickLevel = levels[p.key];
          const pePb = fmtPePb(tickLevel?.pe, tickLevel?.pb);
          const dotColor = {
            green: SEG_COLORS.heavy,
            yellow: SEG_COLORS.add,
            orange: SEG_COLORS.reduce,
            red: SEG_COLORS.full,
          }[meta.color];
          const yld = calcYieldAtPrice(dividend2025, p.price);
          const isOpen = openYield === p.key;
          const row = levelRows[idx] ?? 0;
          return (
            <div
              key={p.key}
              className="absolute inset-y-0 w-0 z-[1]"
              style={{ left: `${left}%` }}
            >
              <div
                className="absolute left-0 -translate-x-1/2 whitespace-nowrap text-center pointer-events-none"
                style={{ top: row === 0 ? 0 : '0.85rem' }}
              >
                <div className="font-mono font-semibold text-xs text-ink tabular-nums">¥{fmtPrice(p.price)}</div>
              </div>
              <button
                type="button"
                title={`${meta.tag} · 点击看股息率`}
                aria-expanded={isOpen}
                aria-label={`${meta.tag} ¥${fmtPrice(p.price)}，点击看股息率`}
                className="absolute left-0 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center w-11 h-11 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full motion-safe:hover:scale-105 motion-safe:transition-transform motion-safe:duration-200"
                style={{ top: 'calc(1.75rem + 7px)' }}
                onClick={e => {
                  e.stopPropagation();
                  setOpenYield(prev => (prev === p.key ? null : p.key));
                }}
              >
                <span
                  className="block rounded-full border-2 border-paper-card shadow-sm"
                  style={{ width: '10px', height: '10px', backgroundColor: dotColor }}
                />
              </button>
              {pePb && (
                <div className="absolute left-0 -translate-x-1/2 top-[calc(1.75rem+14px+8px)] whitespace-nowrap text-center pointer-events-none">
                  <div className="font-mono text-[10px] text-ink-muted tabular-nums">{pePb}</div>
                </div>
              )}
              {isOpen && (
                <YieldPopover
                  title={`${meta.tag}档`}
                  price={p.price}
                  yieldPct={yld}
                  align={popoverAlign(left)}
                  onClose={closeYield}
                />
              )}
            </div>
          );
        })}

        {/* 现价点 */}
        {(() => {
          const yld = calcYieldAtPrice(dividend2025, currentPrice);
          const isOpen = openYield === 'current';
          return (
            <div
              className="absolute inset-y-0 w-0 z-10"
              style={{ left: `${markerLeftPct}%` }}
            >
              <div
                className="absolute left-0 -translate-x-1/2 whitespace-nowrap text-center pointer-events-none"
                style={{ top: currentRow === 0 ? 0 : '0.85rem' }}
              >
                <div className="text-accent font-mono font-bold text-sm tabular-nums drop-shadow-sm">
                  ¥{fmtPrice(currentPrice)}
                </div>
              </div>
              <div
                className="absolute left-0 -translate-x-1/2 w-0.5 bg-accent opacity-70 pointer-events-none"
                style={{ top: currentRow === 0 ? '1.2rem' : '1.9rem', height: currentRow === 0 ? '1.35rem' : '0.65rem' }}
              />
              <button
                type="button"
                title="现价 · 点击看股息率"
                aria-expanded={isOpen}
                aria-label={`现价 ¥${fmtPrice(currentPrice)}，点击看股息率`}
                className="absolute left-0 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center w-11 h-11 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full motion-safe:hover:scale-105 motion-safe:transition-transform motion-safe:duration-200"
                style={{ top: 'calc(1.75rem + 7px)' }}
                onClick={e => {
                  e.stopPropagation();
                  setOpenYield(prev => (prev === 'current' ? null : 'current'));
                }}
              >
                <span className="relative block" style={{ width: '16px', height: '16px' }}>
                  <span className="absolute inset-0 rounded-full bg-accent shadow-md" />
                  <span className="absolute inset-[3px] rounded-full bg-paper-card" />
                  <span className="absolute inset-[5.5px] rounded-full bg-accent" />
                </span>
              </button>
              <div className="absolute left-0 -translate-x-1/2 top-[calc(1.75rem+14px+10px)] whitespace-nowrap text-center pointer-events-none">
                <div className="text-accent font-mono text-[11px] font-medium tabular-nums">
                  {currentPE != null ? `PE ${currentPE.toFixed(1)}` : 'PE -'}
                  {' / '}
                  {currentPB != null ? `PB ${currentPB.toFixed(2)}` : 'PB -'}
                </div>
              </div>
              {isOpen && (
                <YieldPopover
                  title="现价"
                  price={currentPrice}
                  yieldPct={yld}
                  yieldTtm={yieldTtm}
                  accent
                  align={popoverAlign(markerLeftPct)}
                  onClose={closeYield}
                />
              )}
            </div>
          );
        })()}

        {/* 五区名：色条下方，对齐各段中心 */}
        <div className="absolute left-0 right-0 bottom-0 h-4 pointer-events-none">
          {segments.map((seg, i) => {
            if (seg.width < 8) return null;
            const mid = seg.left + seg.width / 2;
            return (
              <div
                key={`${seg.side}-${i}`}
                className="absolute top-0 -translate-x-1/2 whitespace-nowrap"
                style={{ left: `${mid}%` }}
              >
                <span className="inline-flex items-center gap-1 text-[10px] text-ink-muted">
                  <span
                    className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: SEG_COLORS[seg.side] }}
                    aria-hidden
                  />
                  {SEG_LABELS[seg.side]}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function YieldPopover({
  title,
  price,
  yieldPct,
  yieldTtm,
  accent,
  align = 'center',
  onClose,
}: {
  title: string;
  price: number;
  yieldPct: number | null;
  yieldTtm?: number | null;
  accent?: boolean;
  align?: 'left' | 'center' | 'right';
  onClose: () => void;
}) {
  const alignCls =
    align === 'left'
      ? 'left-0 translate-x-0'
      : align === 'right'
        ? 'left-0 -translate-x-full'
        : 'left-0 -translate-x-1/2';

  return (
    <div
      className={`absolute ${alignCls} top-[calc(1.75rem+14px+28px)] z-20 w-max max-w-[11rem] rounded border border-rule bg-paper-card px-2.5 py-2 shadow-md`}
      onClick={e => e.stopPropagation()}
      role="dialog"
      aria-label={`${title}股息率`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className={`text-[10px] font-semibold tracking-wide ${accent ? 'text-accent' : 'text-ink-muted'}`}>
          {title} · 股息率
        </span>
        <button
          type="button"
          className="text-[10px] text-ink-muted hover:text-ink leading-none cursor-pointer"
          onClick={e => {
            e.stopPropagation();
            onClose();
          }}
          aria-label="关闭"
        >
          ×
        </button>
      </div>
      {yieldPct != null ? (
        <div className={`font-mono font-bold text-lg leading-none tabular-nums ${yieldTone(yieldPct)}`}>
          {yieldPct.toFixed(2)}
          <span className="text-xs ml-0.5">%</span>
        </div>
      ) : (
        <div className="font-mono text-sm text-ink-muted">—</div>
      )}
      <div className="text-[9px] text-ink-muted mt-1 font-mono">
        2025分红 / ¥{fmtPrice(price)}
      </div>
      {yieldTtm != null && (
        <div className="text-[10px] text-ink-muted mt-1.5 border-t border-dashed border-rule pt-1.5">
          TTM{' '}
          <span className={`font-mono font-semibold tabular-nums ${yieldTone(yieldTtm)}`}>
            {yieldTtm.toFixed(2)}%
          </span>
        </div>
      )}
    </div>
  );
}
