/**
 * AlertLevelBar — 单只股票的水平价位条
 *
 * 紧凑布局：
 *   L1 股票头：代码/名 + 距各档 + 现价/涨幅/操作建议
 *   L2 色条 + 当前价指针（价格与 PE/PB 同一行）
 *   L3 档位刻度（tag + 价格）；点击档位弹出该档 PE/PB
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
  onClick?: () => void;
}

type LevelKey = 'heavy_position' | 'add_position' | 'reduce_position' | 'full_exit';

// 4 档价格 → 操作建议（色条 + 徽章共用元数据）
const LEVEL_META: Record<LevelKey, { tag: string; shortLabel: string; color: 'green' | 'yellow' | 'orange' | 'red' }> = {
  heavy_position:  { tag: '重仓', shortLabel: '重仓', color: 'green'  },
  add_position:    { tag: '加仓', shortLabel: '加仓', color: 'yellow' },
  reduce_position: { tag: '减仓', shortLabel: '减仓', color: 'orange' },
  full_exit:       { tag: '全卖', shortLabel: '全卖', color: 'red'    },
};

// 5 段色块颜色（暖白色板下低饱和暖色 + 中性灰持有区）
// 持有区用 paper-deep 的加深一档，与"持有观望"徽章语义一致
const SEG_COLORS: Record<'heavy' | 'add' | 'hold' | 'reduce' | 'full', string> = {
  heavy:  '#5A9472', // 暖绿
  add:    '#C9951F', // 暖黄
  hold:   '#D9D2C2', // 中性灰（持有区，介于 paper-deep 与 rule-strong 之间）
  reduce: '#B85C38', // 暖橙
  full:   '#A8453A', // 暖红
};

// 段位语义判定：根据相邻两档的"买/卖方向"决定段色
// - 两端段（首/尾）：用单边档位的色
// - 中间段：两档同买→用右档色（更高）；两档同卖→用左档色（更低）；买→卖→持有
// 这样即使只设 2/3 档（缺档），色段仍按"有意义的相邻区"渲染，不出 NaN/空段
function gapColor(
  leftKey: LevelKey | null,
  rightKey: LevelKey | null
): 'heavy' | 'add' | 'hold' | 'reduce' | 'full' {
  const keyToSeg = (k: LevelKey): 'heavy' | 'add' | 'reduce' | 'full' => {
    if (k === 'heavy_position')  return 'heavy';
    if (k === 'add_position')    return 'add';
    if (k === 'reduce_position') return 'reduce';
    return 'full';
  };
  const isBuy = (k: LevelKey) => k === 'heavy_position' || k === 'add_position';
  const isSell = (k: LevelKey) => k === 'reduce_position' || k === 'full_exit';

  // 边界段：仅一边有 key
  if (!leftKey && rightKey) return keyToSeg(rightKey);
  if (leftKey && !rightKey) return keyToSeg(leftKey);

  // 中间段：两边都有 key
  if (leftKey && rightKey) {
    if (isBuy(leftKey) && isBuy(rightKey))   return keyToSeg(rightKey); // 重仓→加仓 / 加仓→重仓：用较高价档色
    if (isSell(leftKey) && isSell(rightKey)) return keyToSeg(leftKey);  // 减仓→全卖 / 全卖→减仓：用较低价档色
    if (isBuy(leftKey) && isSell(rightKey))  return 'hold';             // 加仓→减仓：持有区
  }
  return 'hold';
}

// 命中状态：5 个色块 + 持有观望
type HitStatus = 'heavy' | 'add' | 'hold' | 'reduce' | 'full' | 'inactive';

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

// 命中徽章暖白配色（底色 -50 + 文字 -700 + 边框 -200）
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
  onClick,
}: AlertLevelBarProps) {
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

  // 关键：只用已设置档位的价格作为区间，不把 currentPrice 算进 min/max
  // 否则 currentPrice 在区间内时 minP==heavy / maxP==full，首/末段会被压成 0 宽度
  const minP = Math.min(...points.map(p => p.price));
  const maxP = Math.max(...points.map(p => p.price));
  const range = maxP - minP || 1;
  // pct clamp 到 [5, 95]：首/末段保底 5% 宽度，避免被压成 0 宽度而视觉消失
  const pct = (p: number) => Math.max(5, Math.min(95, ((p - minP) / range) * 100));

  // 4 档价格按价位排序
  const sortedPoints = [...points].sort((a, b) => a.price - b.price);

  // 动态生成色段：基于实际设置的价格点数（2-4 档都支持）
  // - 4 档：5 段（heavy/add/hold/reduce/full）
  // - 3 档：4 段（按相邻语义合并缺失档位的色）
  // - 2 档：3 段
  // 不再硬编码 sortedPoints[0..3]，避免缺档时 NaN 段导致 5 段变 3 段
  const segments: Array<{ side: 'heavy' | 'add' | 'hold' | 'reduce' | 'full'; left: number; width: number }> = [];
  if (sortedPoints.length >= 1) {
    // 首段：[0, p0] 用 p0 的色
    segments.push({
      side: gapColor(null, sortedPoints[0].key),
      left: 0,
      width: pct(sortedPoints[0].price),
    });
    // 中间段：[pi, pi+1] 按相邻语义着色
    for (let i = 0; i < sortedPoints.length - 1; i++) {
      const leftPct = pct(sortedPoints[i].price);
      const rightPct = pct(sortedPoints[i + 1].price);
      const width = rightPct - leftPct;
      if (width <= 0) continue; // 两档同价时跳过 0 宽段
      segments.push({
        side: gapColor(sortedPoints[i].key, sortedPoints[i + 1].key),
        left: leftPct,
        width,
      });
    }
    // 末段：[pn, max] 用 pn 的色
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

  // 命中涨跌幅（vs 距离最近的有效档算）
  const change = (() => {
    if (points.length === 0) return null;
    const sortedByPrice = [...points].sort((a, b) => a.price - b.price);
    const closest = sortedByPrice.reduce((prev, p) =>
      Math.abs(p.price - currentPrice) < Math.abs(prev.price - currentPrice) ? p : prev
    );
    if (closest.price === 0) return null;
    return ((currentPrice - closest.price) / closest.price) * 100;
  })();

  // 各档距离 %（按距离最近的有效档算）
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

  // 当前价 ▲ 标签水平位置：clamp 到 [8%, 92%]，避免文字溢出卡片边界
  const markerLeftPct = Math.max(8, Math.min(92, pct(currentPrice)));

  const [openPePbKey, setOpenPePbKey] = useState<LevelKey | null>(null);

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

      {/* L2 色条 + 当前价标识（价格标在色条上方一行） */}
      <div className="relative pt-5">
        <div className="relative h-2 bg-paper-deep rounded-full overflow-hidden">
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

        <div
          className="absolute inset-0 pointer-events-none"
          aria-label={`当前价 ${fmtPrice(currentPrice)}`}
        >
          <div
            className="absolute w-0.5 bg-accent opacity-60"
            style={{
              left: `${markerLeftPct}%`,
              transform: 'translateX(-50%)',
              top: '1.25rem',
              bottom: 0,
            }}
          />
          <div
            className="absolute"
            style={{
              left: `${markerLeftPct}%`,
              top: 'calc(1.25rem + 4px)',
              transform: 'translate(-50%, -50%)',
              width: '12px',
              height: '12px',
            }}
          >
            <div className="absolute inset-0 rounded-full bg-accent" />
            <div className="absolute inset-[2.5px] rounded-full bg-paper-card shadow-sm" />
            <div className="absolute inset-[4.5px] rounded-full bg-accent" />
          </div>
          <div
            className="absolute whitespace-nowrap"
            style={{
              left: `${markerLeftPct}%`,
              top: 0,
              transform: 'translateX(-50%)',
            }}
          >
            <span className="text-accent font-mono font-bold text-[11px]">¥{fmtPrice(currentPrice)}</span>
            <span className="text-accent-hover font-mono text-[10px] opacity-80 ml-1">
              {currentPE != null ? `PE ${currentPE.toFixed(1)}` : 'PE -'}
              {' / '}
              {currentPB != null ? `PB ${currentPB.toFixed(2)}` : 'PB -'}
            </span>
          </div>
        </div>
      </div>

      {/* L3 档位刻度：仅 tag + 价格；点击档位弹出该档 PE/PB */}
      <div className="relative h-8 mt-1.5">
        {sortedPoints.map(p => {
          const meta = LEVEL_META[p.key];
          const tagClass = {
            green: 'bg-green-50 text-green-700 border-green-200',
            yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
            orange: 'bg-orange-50 text-orange-700 border-orange-200',
            red: 'bg-red-50 text-red-700 border-red-200',
          }[meta.color];
          const tickLeftPct = Math.max(4, Math.min(96, pct(p.price)));
          const tickLevel = levels[p.key];
          const tickPE = tickLevel?.pe ?? null;
          const tickPB = tickLevel?.pb ?? null;
          const isOpen = openPePbKey === p.key;
          return (
            <div
              key={p.key}
              className="absolute -translate-x-1/2 text-center"
              style={{ left: `${tickLeftPct}%` }}
            >
              <button
                type="button"
                title="点击查看该档 PE/PB"
                aria-expanded={isOpen}
                className="inline-flex flex-col items-center cursor-pointer hover:opacity-80"
                onClick={e => {
                  e.stopPropagation();
                  setOpenPePbKey(prev => (prev === p.key ? null : p.key));
                }}
              >
                <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-semibold border ${tagClass}`}>
                  {meta.tag}
                </span>
                <div className="text-ink font-mono font-semibold text-[11px] mt-0.5">¥{fmtPrice(p.price)}</div>
              </button>
              {isOpen && (
                <div
                  className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-10 whitespace-nowrap rounded border border-rule bg-paper-card px-2 py-1 shadow-sm font-mono text-[10px] text-ink"
                  onClick={e => e.stopPropagation()}
                >
                  {tickPE != null ? `PE ${tickPE.toFixed(1)}` : 'PE -'}
                  {' / '}
                  {tickPB != null ? `PB ${tickPB.toFixed(2)}` : 'PB -'}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}