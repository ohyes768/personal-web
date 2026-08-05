/**
 * AlertLevelBar — 单只股票的水平价位条
 *
 * 5 段色块（重仓区 / 加仓区 / 持有区 / 减仓区 / 全卖区）+ ▲ 蓝色三角指针（当前价）+ 4 档价格刻度（每档 PE/PB）+ 命中状态 badge
 *
 * 色块位置按 4 档价格归一化百分比，按当前价绘制 ▲ 指针
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

const LEVEL_META: Record<LevelKey, { tag: string; color: 'green' | 'yellow' | 'orange' | 'red'; shortLabel: string }> = {
  heavy_position:  { tag: '🟢 重仓', color: 'green',  shortLabel: '重仓' },
  add_position:    { tag: '🟡 加仓', color: 'yellow', shortLabel: '加仓' },
  reduce_position: { tag: '🟠 减仓', color: 'orange', shortLabel: '减仓' },
  full_exit:       { tag: '🔴 全卖', color: 'red',    shortLabel: '全卖' },
};

const ZONE_LABELS = [
  { key: 'heavy',  text: '重仓区', color: 'text-green-400',  side: 'heavy' },
  { key: 'add',    text: '加仓区', color: 'text-yellow-400', side: 'add' },
  { key: 'hold',   text: '持有区', color: 'text-slate-400',  side: 'add' },
  { key: 'reduce', text: '减仓区', color: 'text-orange-400', side: 'reduce' },
  { key: 'full',   text: '全卖区', color: 'text-red-400',    side: 'full' },
];

const ZONE_SEGMENT_CLASS: Record<string, string> = {
  heavy:  'bg-green-500',
  add:    'bg-yellow-500',
  hold:   'bg-slate-500',
  reduce: 'bg-orange-500',
  full:   'bg-red-500',
};

const ZONE_SEGMENT_OPACITY: Record<string, string> = {
  heavy: 'opacity-90',
  add: 'opacity-90',
  hold: 'opacity-60',
  reduce: 'opacity-90',
  full: 'opacity-90',
};

interface PricePoint {
  key: LevelKey;
  price: number;
  pe?: number | null;
  pb?: number | null;
}

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

const HIT_META: Record<HitStatus, { label: string; cls: string } | null> = {
  heavy: { label: '🟢 重仓命中', cls: 'bg-green-900/50 text-green-300 border border-green-700' },
  add: { label: '🟡 加仓命中', cls: 'bg-yellow-900/50 text-yellow-300 border border-yellow-700' },
  reduce: { label: '🟠 减仓命中', cls: 'bg-orange-900/50 text-orange-300 border border-orange-700' },
  full: { label: '🔴 全卖命中', cls: 'bg-red-900/50 text-red-300 border border-red-700' },
  hold: null,
  inactive: null,
};

function fmtPrice(p: number): string {
  return p.toFixed(2);
}

function fmtPct(p: number): string {
  const sign = p > 0 ? '+' : '';
  return `${sign}${p.toFixed(1)}%`;
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
        list.push({ key: k, price: lv.price, pe: lv.pe, pb: lv.pb });
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

  // 5 段色块：(0, p1, p2, p3, p4, +∞)
  // 最小段: ≤ min(4 档)
  // 最大段: ≥ max(4 档)
  // 中间 3 段: 每对相邻价格之间
  const segments = [
    { side: 'heavy',  left: 0,                       width: pct(sortedPoints[0].price) },
    { side: 'add',    left: pct(sortedPoints[0].price), width: pct(sortedPoints[1].price) - pct(sortedPoints[0].price) },
    { side: 'hold',   left: pct(sortedPoints[1].price), width: pct(sortedPoints[2].price) - pct(sortedPoints[1].price) },
    { side: 'reduce', left: pct(sortedPoints[2].price), width: pct(sortedPoints[3].price) - pct(sortedPoints[2].price) },
    { side: 'full',   left: pct(sortedPoints[3].price), width: 100 - pct(sortedPoints[3].price) },
  ];

  const status = hitStatus(levels, currentPrice);
  const badge = HIT_META[status];

  // 命中涨跌幅（vs 上一档价格偏移）
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
  const distances = sortedPoints.map(p => ({
    key: p.key,
    price: p.price,
    pct: p.price > 0 ? ((currentPrice - p.price) / p.price) * 100 : 0,
  }));

  return (
    <div
      className={`bg-paper-card border border-rule rounded-lg p-4 ${onClick ? 'cursor-pointer hover:border-rule-strong transition-colors' : ''}`}
      onClick={onClick}
      data-code={code}
    >
      {/* 头部：股票 + 现价 + 命中状态 */}
      <div className="flex items-center gap-3 mb-3">
        <span className="font-semibold text-ink">{code}</span>
        <span className="text-ink-muted text-sm">{name}</span>
        <span className="font-mono font-semibold text-ink ml-auto">¥{fmtPrice(currentPrice)}</span>
        {change !== null && (
          <span className={`font-mono text-xs ${change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {fmtPct(change)}
          </span>
        )}
        {badge && (
          <span className={`text-xs px-2 py-0.5 rounded ${badge.cls}`}>
            {badge.label}
          </span>
        )}
      </div>

      {/* 区位标签（条上方） */}
      <div className="relative h-4 mb-1">
        {ZONE_LABELS.map((zl, i) => {
          const seg = segments[i];
          if (!seg || seg.width < 5) return null;
          const center = seg.left + seg.width / 2;
          return (
            <div
              key={zl.key}
              className={`absolute text-[10px] font-medium transform -translate-x-1/2 ${zl.color}`}
              style={{ left: `${center}%` }}
            >
              {zl.text}
            </div>
          );
        })}
      </div>

      {/* 5 段色块 + ▲ 三角指针 */}
      <div className="relative">
        <div className="relative h-2 bg-slate-700 rounded-full overflow-hidden">
          {segments.map((seg, i) => (
            <div
              key={i}
              className={`absolute top-0 bottom-0 ${ZONE_SEGMENT_CLASS[seg.side]} ${ZONE_SEGMENT_OPACITY[seg.side]}`}
              style={{ left: `${seg.left}%`, width: `${seg.width}%` }}
            />
          ))}
        </div>

        {/* 当前价 ▲ 三角（条上方） */}
        <div
          className="absolute -top-1 transform -translate-x-1/2 flex flex-col items-center"
          style={{ left: `${pct(currentPrice)}%` }}
        >
          <div className="text-indigo-400 text-sm leading-none">▲</div>
        </div>

        {/* 当前价标签（在三角上方） */}
        <div
          className="absolute -top-10 transform -translate-x-1/2 text-center whitespace-nowrap"
          style={{ left: `${pct(currentPrice)}%` }}
        >
          <div className="text-indigo-400 font-mono font-bold text-xs">¥{fmtPrice(currentPrice)}</div>
          {(currentPE != null || currentPB != null) && (
            <div className="text-indigo-300 font-mono text-[10px]">
              {currentPE != null ? `PE ${currentPE.toFixed(1)}` : 'PE -'}
              {' / '}
              {currentPB != null ? `PB ${currentPB.toFixed(2)}` : 'PB -'}
            </div>
          )}
        </div>
      </div>

      {/* 4 档价格刻度（条下方） */}
      <div className="relative h-14 mt-2">
        {sortedPoints.map(p => {
          const meta = LEVEL_META[p.key];
          const tagClass = {
            green: 'bg-green-900/40 text-green-300 border-green-700',
            yellow: 'bg-yellow-900/40 text-yellow-300 border-yellow-700',
            orange: 'bg-orange-900/40 text-orange-300 border-orange-700',
            red: 'bg-red-900/40 text-red-300 border-red-700',
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
              <div className="text-ink-muted font-mono text-[10px]">
                {p.pe != null ? `PE ${p.pe.toFixed(1)}` : 'PE -'}
                {' / '}
                {p.pb != null ? `PB ${p.pb.toFixed(2)}` : 'PB -'}
              </div>
            </div>
          );
        })}
      </div>

      {/* 距离行 */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-ink-muted pt-3 mt-1 border-t border-dashed border-rule">
        {distances.map(d => {
          const meta = LEVEL_META[d.key];
          const isHit = (() => {
            if (d.key === 'heavy_position' || d.key === 'add_position') {
              return currentPrice <= d.price;
            }
            return currentPrice >= d.price;
          })();
          const isNear = Math.abs(d.pct) < 10;
          return (
            <span key={d.key}>
              距 {meta.shortLabel}{' '}
              <span className={isHit ? 'text-green-400 font-semibold' : isNear ? 'text-yellow-400' : ''}>
                {fmtPct(d.pct)}{isHit ? ' ✓' : ''}
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
