/**
 * AlertLevelBar — 单只股票的水平价位条
 *
 * 3 层信息结构（决策 / 位置 / 参考）：
 *   L1 股票头：代码/名/现价/涨幅/操作建议徽章
 *   L2 4 段色条（价格区间）+ ▲ 三角指针（当前价 + PE/PB）
 *   L3 4 档价格刻度（tag + 价格，无 PE/PB 冗余）+ 距离行（3 级色阶）
 *
 * 色彩通道单一职责：
 *   - 色条只表达"价格在哪一档"，4 段渐变（左低右高，颜色由暖绿→暖黄→暖橙→暖红）
 *   - 命中徽章单独表达"该怎么做"，直白动词
 */

'use client';

import { useMemo } from 'react';
import type { AlertLevel, AlertLevels } from '@/lib/types';

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

// 4 段色块颜色（暖白色板下低饱和暖色）
const SEG_COLORS: Record<'heavy' | 'add' | 'reduce' | 'full', string> = {
  heavy:  '#5A9472', // 暖绿
  add:    '#C9951F', // 暖黄
  reduce: '#B85C38', // 暖橙
  full:   '#A8453A', // 暖红
};

// 命中状态：5 个色块 + 持有观望（无独立色段，徽章表达）
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

  const minP = Math.min(...points.map(p => p.price), currentPrice);
  const maxP = Math.max(...points.map(p => p.price), currentPrice);
  const range = maxP - minP || 1;
  const pct = (p: number) => Math.max(0, Math.min(100, ((p - minP) / range) * 100));

  // 4 档价格按价位排序
  const sortedPoints = [...points].sort((a, b) => a.price - b.price);

  // 4 段色块：[p0,p1][p1,p2][p2,p3] 三个内部段；首尾两段用淡背景表示外延
  const segments = [
    { side: 'heavy'  as const, left: pct(sortedPoints[0].price),                                  width: pct(sortedPoints[1].price) - pct(sortedPoints[0].price) },
    { side: 'add'    as const, left: pct(sortedPoints[1].price),                                  width: pct(sortedPoints[2].price) - pct(sortedPoints[1].price) },
    { side: 'reduce' as const, left: pct(sortedPoints[2].price),                                  width: pct(sortedPoints[3].price) - pct(sortedPoints[2].price) },
    { side: 'full'   as const, left: pct(sortedPoints[3].price),                                  width: 100 - pct(sortedPoints[3].price) },
  ];

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

  return (
    <div
      className={`bg-paper-card border border-rule rounded-lg p-4 ${onClick ? 'cursor-pointer hover:border-rule-strong transition-colors' : ''}`}
      onClick={onClick}
      data-code={code}
    >
      {/* L1 头部：股票 + 现价 + 操作建议徽章（决策通道） */}
      <div className="flex items-center gap-3 mb-3">
        <span className="font-semibold text-ink">{code}</span>
        <span className="text-ink-muted text-sm">{name}</span>
        <span className="font-mono font-semibold text-ink ml-auto">¥{fmtPrice(currentPrice)}</span>
        {change !== null && (
          <span className={`font-mono text-xs ${change >= 0 ? 'text-up' : 'text-down'}`}>
            {fmtPct(change)}
          </span>
        )}
        {badge && (
          <span className={`text-xs px-2 py-0.5 rounded whitespace-nowrap ${badge.cls}`}>
            {badge.label}
          </span>
        )}
      </div>

      {/* L2 4 段色条 + ▲ 三角指针（位置通道） */}
      <div className="relative">
        <div className="relative h-2.5 bg-paper-deep rounded-full overflow-hidden">
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

        {/* 当前价 ▲ 三角（色条上方） */}
        <div
          className="absolute -top-1.5 transform -translate-x-1/2 text-accent text-sm leading-none"
          style={{ left: `${markerLeftPct}%` }}
        >
          ▲
        </div>

        {/* 当前价标签（▲ 上方，clamp 避免溢出） */}
        <div
          className="absolute -top-9 transform -translate-x-1/2 text-center whitespace-nowrap"
          style={{ left: `${markerLeftPct}%` }}
        >
          <div className="text-accent font-mono font-bold text-xs">¥{fmtPrice(currentPrice)}</div>
          {(currentPE != null || currentPB != null) && (
            <div className="text-accent-hover font-mono text-[10px] opacity-80">
              {currentPE != null ? `PE ${currentPE.toFixed(1)}` : 'PE -'}
              {' / '}
              {currentPB != null ? `PB ${currentPB.toFixed(2)}` : 'PB -'}
            </div>
          )}
        </div>
      </div>

      {/* L3 4 档价格刻度（参考通道：tag + 价格，去掉 PE/PB 冗余） */}
      <div className="relative h-10 mt-3">
        {sortedPoints.map(p => {
          const meta = LEVEL_META[p.key];
          const tagClass = {
            green: 'bg-green-50 text-green-700 border-green-200',
            yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
            orange: 'bg-orange-50 text-orange-700 border-orange-200',
            red: 'bg-red-50 text-red-700 border-red-200',
          }[meta.color];
          return (
            <div
              key={p.key}
              className="absolute -translate-x-1/2 text-center"
              style={{ left: `${pct(p.price)}%` }}
            >
              <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-semibold border ${tagClass}`}>
                {meta.tag}
              </span>
              <div className="text-ink font-mono font-semibold text-xs mt-0.5">¥{fmtPrice(p.price)}</div>
            </div>
          );
        })}
      </div>

      {/* 距离行：3 级色阶 */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono pt-3 mt-1 border-t border-dashed border-rule">
        {distances.map(d => {
          const meta = LEVEL_META[d.key];
          const tone = distTone(d.pct, d.isHit);
          return (
            <span key={d.key} className={tone.cls}>
              距 {meta.shortLabel} {fmtPct(d.pct)}{tone.suffix}
            </span>
          );
        })}
      </div>
    </div>
  );
}