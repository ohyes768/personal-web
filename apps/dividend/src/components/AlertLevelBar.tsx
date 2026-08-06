/**
 * AlertLevelBar — 单只股票的水平价位条
 *
 * 紧凑布局：
 *   L1 股票头：代码/名 + 距各档 + 现价/涨幅/操作建议
 *   L2 五区色条 + 5 个点（现价醒目 + 4 档）：上方价格，下方 PE/PB
 *   点击点：弹出该价位股息率（2025 分红 / 价格，与表格「实时股息率」同口径）
 */

'use client';

import { useMemo, useState } from 'react';
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
  onClick?: () => void;
}

type LevelKey = 'heavy_position' | 'add_position' | 'reduce_position' | 'full_exit';
type SegSide = 'heavy' | 'add' | 'hold' | 'reduce' | 'full';

// 4 档价格 → 操作建议（色条 + 徽章共用元数据）
const LEVEL_META: Record<LevelKey, { tag: string; shortLabel: string; color: 'green' | 'yellow' | 'orange' | 'red' }> = {
  heavy_position:  { tag: '重仓', shortLabel: '重仓', color: 'green'  },
  add_position:    { tag: '加仓', shortLabel: '加仓', color: 'yellow' },
  reduce_position: { tag: '减仓', shortLabel: '减仓', color: 'orange' },
  full_exit:       { tag: '全卖', shortLabel: '全卖', color: 'red'    },
};

// 5 段色块颜色（暖白色板；减仓偏橙、全卖偏深红，拉开 4/5 段对比）
const SEG_COLORS: Record<SegSide, string> = {
  heavy:  '#5A9472', // 暖绿
  add:    '#C9951F', // 暖黄
  hold:   '#D9D2C2', // 中性灰（持有区）
  reduce: '#D4893A', // 暖琥珀橙（减仓）
  full:   '#9B2F2F', // 深红（全卖，与减仓拉开）
};

// 色块上的五区标签
const SEG_LABELS: Record<SegSide, string> = {
  heavy:  '重仓区',
  add:    '加仓区',
  hold:   '持有区',
  reduce: '减仓区',
  full:   '全卖区',
};

// 色块标签字色：持有区浅底用深字，其余深色块用白字
const SEG_LABEL_CLS: Record<SegSide, string> = {
  heavy:  'text-white/95',
  add:    'text-white/95',
  hold:   'text-ink-muted',
  reduce: 'text-white/95',
  full:   'text-white/95',
};

// 段位语义判定：根据相邻两档的"买/卖方向"决定段色
// - 两端段（首/尾）：用单边档位的色
// - 中间段：两档同买→用右档色（更高）；两档同卖→用左档色（更低）；买→卖→持有
function gapColor(leftKey: LevelKey | null, rightKey: LevelKey | null): SegSide {
  const keyToSeg = (k: LevelKey): Exclude<SegSide, 'hold'> => {
    if (k === 'heavy_position')  return 'heavy';
    if (k === 'add_position')    return 'add';
    if (k === 'reduce_position') return 'reduce';
    return 'full';
  };
  const isBuy = (k: LevelKey) => k === 'heavy_position' || k === 'add_position';
  const isSell = (k: LevelKey) => k === 'reduce_position' || k === 'full_exit';

  if (!leftKey && rightKey) return keyToSeg(rightKey);
  if (leftKey && !rightKey) return keyToSeg(leftKey);

  if (leftKey && rightKey) {
    if (isBuy(leftKey) && isBuy(rightKey))   return keyToSeg(rightKey);
    if (isSell(leftKey) && isSell(rightKey)) return keyToSeg(leftKey);
    if (isBuy(leftKey) && isSell(rightKey))  return 'hold';
  }
  return 'hold';
}

// 命中状态：5 个色块 + 持有观望
type HitStatus = SegSide | 'inactive';

function hitStatus(levels: AlertLevels, currentPrice: number): HitStatus {
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

const HIT_META: Record<HitStatus, { label: string; cls: string } | null> = {
  heavy:  { label: '🟢 可加仓',    cls: 'bg-green-50 text-green-700 border border-green-200' },
  add:    { label: '🟡 加仓价位',  cls: 'bg-yellow-50 text-yellow-700 border border-yellow-200' },
  reduce: { label: '🟠 该减仓',    cls: 'bg-orange-50 text-orange-700 border border-orange-200' },
  full:   { label: '🔴 全部清仓',  cls: 'bg-red-50 text-red-700 border border-red-200' },
  hold:   { label: '⏸ 持有观望',  cls: 'bg-slate-50 text-slate-600 border border-slate-200' },
  inactive: null,
};

interface PricePoint {
  key: LevelKey;
  price: number;
}

function fmtPrice(p: number): string {
  return p.toFixed(2);
}

function fmtPct(p: number): string {
  const sign = p > 0 ? '+' : '';
  return `${sign}${p.toFixed(1)}%`;
}

/** 选填 PE/PB：有哪个标哪个，都没有返回 null */
function fmtPePb(pe?: number | null, pb?: number | null): string | null {
  const parts: string[] = [];
  if (pe != null) parts.push(`PE ${pe.toFixed(1)}`);
  if (pb != null) parts.push(`PB ${pb.toFixed(2)}`);
  return parts.length > 0 ? parts.join(' / ') : null;
}

/** 与表格「实时股息率」同口径：年度分红 / 价格 × 100% */
function calcYieldAtPrice(dividend: number | null | undefined, price: number): number | null {
  if (dividend == null || dividend <= 0 || price <= 0) return null;
  return (dividend / price) * 100;
}

function yieldTone(y: number): string {
  if (y >= 5) return 'text-emerald-700';
  if (y >= 3) return 'text-emerald-600';
  return 'text-ink';
}

type YieldKey = LevelKey | 'current';

/**
 * 距离行三级色阶：
 *   <5%  红色字 + ✓（已命中或极近）
 *   5-10% 黄色字（接近）
 *   >10% 默认灰（远）
 */
function distTone(pct: number, isHit: boolean): { cls: string; suffix: string } {
  if (isHit || Math.abs(pct) < 5) {
    return { cls: 'text-red-600 font-semibold', suffix: ' ✓' };
  }
  if (Math.abs(pct) < 10) {
    return { cls: 'text-yellow-700', suffix: '' };
  }
  return { cls: 'text-ink-muted', suffix: '' };
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
  onClick,
}: AlertLevelBarProps) {
  const [openYield, setOpenYield] = useState<YieldKey | null>(null);

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
    // 至少 2 档价格才能画水平条
    return null;
  }

  // 尺度：只用已设置档位的价格作为区间，不把 currentPrice 算进 min/max
  const minP = Math.min(...points.map(p => p.price));
  const maxP = Math.max(...points.map(p => p.price));
  const range = maxP - minP || 1;
  // pct clamp 到 [5, 95]：首/末段保底 5% 宽度，避免被压成 0 宽度而视觉消失
  const pct = (p: number) => Math.max(5, Math.min(95, ((p - minP) / range) * 100));

  const sortedPoints = [...points].sort((a, b) => a.price - b.price);

  // 动态生成色段：4 档 → 5 段（重仓/加仓/持有/减仓/全卖）
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
    if (points.length === 0) return null;
    const sortedByPrice = [...points].sort((a, b) => a.price - b.price);
    const closest = sortedByPrice.reduce((prev, p) =>
      Math.abs(p.price - currentPrice) < Math.abs(prev.price - currentPrice) ? p : prev
    );
    if (closest.price === 0) return null;
    return ((currentPrice - closest.price) / closest.price) * 100;
  })();

  const distances = sortedPoints.map(p => {
    const isHit = (() => {
      if (p.key === 'heavy_position' || p.key === 'add_position') return currentPrice <= p.price;
      return currentPrice >= p.price;
    })();
    return {
      key: p.key,
      price: p.price,
      pct: p.price > 0 ? ((currentPrice - p.price) / p.price) * 100 : 0,
      isHit,
    };
  });

  const markerLeftPct = Math.max(8, Math.min(92, pct(currentPrice)));

  return (
    <div
      className={`bg-paper-card border border-rule rounded-lg px-3 py-2.5 ${onClick ? 'cursor-pointer hover:border-rule-strong transition-colors' : ''}`}
      onClick={onClick}
      data-code={code}
    >
      {/* L1 头部：股票 + 距各档 + 现价 + 操作建议 */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
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
        <span className="font-mono font-semibold text-ink text-sm ml-auto">¥{fmtPrice(currentPrice)}</span>
        {change !== null && (
          <span className={`font-mono text-[11px] ${change >= 0 ? 'text-up' : 'text-down'}`}>
            {fmtPct(change)}
          </span>
        )}
        {badge && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded whitespace-nowrap ${badge.cls}`}>
            {badge.label}
          </span>
        )}
      </div>

      {/* L2 五区色条 + 5 点：上价格 / 下 PE·PB；点击点看股息率 */}
      <div className="relative pt-5 pb-7">
        <div className="relative h-6 bg-paper-deep rounded-md overflow-hidden">
          {segments.map((seg, i) => (
            <div
              key={i}
              className="absolute top-0 bottom-0 flex items-center justify-center overflow-hidden"
              style={{
                left: `${seg.left}%`,
                width: `${seg.width}%`,
                backgroundColor: SEG_COLORS[seg.side],
              }}
            >
              {seg.width >= 8 && (
                <span className={`text-[10px] font-semibold tracking-wide whitespace-nowrap select-none ${SEG_LABEL_CLS[seg.side]}`}>
                  {SEG_LABELS[seg.side]}
                </span>
              )}
            </div>
          ))}
        </div>

        {/* 4 档位点 */}
        {sortedPoints.map(p => {
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
          return (
            <div
              key={p.key}
              className="absolute inset-y-0 w-0 z-[1]"
              style={{ left: `${left}%` }}
            >
              {/* 上：价格 */}
              <div className="absolute left-0 -translate-x-1/2 top-0 whitespace-nowrap text-center pointer-events-none">
                <div className="font-mono font-semibold text-[10px] text-ink">¥{fmtPrice(p.price)}</div>
              </div>
              {/* 可点热区 + 色点 */}
              <button
                type="button"
                title={`${meta.tag} · 点击看股息率`}
                aria-expanded={isOpen}
                className="absolute left-0 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-paper-card shadow-sm cursor-pointer hover:scale-125 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                style={{
                  top: 'calc(1.25rem + 12px)',
                  width: '14px',
                  height: '14px',
                  backgroundColor: dotColor,
                }}
                onClick={e => {
                  e.stopPropagation();
                  setOpenYield(prev => (prev === p.key ? null : p.key));
                }}
              />
              {/* 下：选填 PE/PB */}
              {pePb && (
                <div className="absolute left-0 -translate-x-1/2 top-[calc(1.25rem+24px+6px)] whitespace-nowrap text-center pointer-events-none">
                  <div className="font-mono text-[9px] text-ink-muted">{pePb}</div>
                </div>
              )}
              {/* 股息率浮层 */}
              {isOpen && (
                <YieldPopover
                  title={`${meta.tag}档`}
                  price={p.price}
                  yieldPct={yld}
                  onClose={() => setOpenYield(null)}
                />
              )}
            </div>
          );
        })}

        {/* 现价点：更大、强调色 */}
        {(() => {
          const yld = calcYieldAtPrice(dividend2025, currentPrice);
          const isOpen = openYield === 'current';
          return (
            <div
              className="absolute inset-y-0 w-0 z-10"
              style={{ left: `${markerLeftPct}%` }}
            >
              <div className="absolute left-0 -translate-x-1/2 top-0 whitespace-nowrap text-center pointer-events-none">
                <div className="text-accent font-mono font-bold text-[11px] drop-shadow-sm">¥{fmtPrice(currentPrice)}</div>
              </div>
              <div
                className="absolute left-0 -translate-x-1/2 w-0.5 bg-accent opacity-70 pointer-events-none"
                style={{ top: '1.05rem', height: '1.55rem' }}
              />
              <button
                type="button"
                title="现价 · 点击看股息率"
                aria-expanded={isOpen}
                aria-label={`现价 ¥${fmtPrice(currentPrice)}`}
                className="absolute left-0 -translate-x-1/2 -translate-y-1/2 cursor-pointer hover:scale-110 transition-transform focus:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                style={{
                  top: 'calc(1.25rem + 12px)',
                  width: '18px',
                  height: '18px',
                }}
                onClick={e => {
                  e.stopPropagation();
                  setOpenYield(prev => (prev === 'current' ? null : 'current'));
                }}
              >
                <span className="absolute inset-0 rounded-full bg-accent shadow-md" />
                <span className="absolute inset-[3px] rounded-full bg-paper-card" />
                <span className="absolute inset-[5.5px] rounded-full bg-accent" />
              </button>
              <div className="absolute left-0 -translate-x-1/2 top-[calc(1.25rem+24px+8px)] whitespace-nowrap text-center pointer-events-none">
                <div className="text-accent font-mono text-[10px] font-medium">
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
                  onClose={() => setOpenYield(null)}
                />
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

/** 股息率浮层：与系统「实时股息率」同口径 */
function YieldPopover({
  title,
  price,
  yieldPct,
  yieldTtm,
  accent,
  onClose,
}: {
  title: string;
  price: number;
  yieldPct: number | null;
  yieldTtm?: number | null;
  accent?: boolean;
  onClose: () => void;
}) {
  return (
    <div
      className="absolute left-0 -translate-x-1/2 top-[calc(1.25rem+24px+22px)] z-20 w-max max-w-[11rem] rounded border border-rule bg-paper-card px-2.5 py-2 shadow-md"
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
          className="text-[10px] text-ink-muted hover:text-ink leading-none"
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
