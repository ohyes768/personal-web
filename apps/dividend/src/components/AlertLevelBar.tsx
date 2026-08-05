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

  const minP = Math.min(...points.map(p => p.price), currentPrice);
  const maxP = Math.max(...points.map(p => p.price), currentPrice);
  const range = maxP - minP || 1;
  const pct = (p: number) => Math.max(0, Math.min(100, ((p - minP) / range) * 100));

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

      {/* L2 4 段色条 + 当前价标识（位置通道） */}
      {/* pt-9 = 36px 顶部内边距，给标签留空间，让色条仍在容器底部 */}
      <div className="relative pt-9">
        {/* 5 段色条 */}
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

        {/* 当前价标识：垂直线 + 双层圆点 + 标签（专业行情光标） */}
        {/* 整组绝对定位覆盖整个 L2 容器（含标签空间），clamp 防溢出 */}
        <div
          className="absolute inset-0 pointer-events-none"
          aria-label={`当前价 ${fmtPrice(currentPrice)}`}
        >
          {/* 垂直线：从标签下方贯穿到色条底部 */}
          <div
            className="absolute w-0.5 bg-accent opacity-60"
            style={{
              left: `${markerLeftPct}%`,
              transform: 'translateX(-50%)',
              top: '2.25rem',  // pt-9 (2.25rem) 之下开始，让线与标签底部对齐
              bottom: 0,
            }}
          />

          {/* 双层焦点圆（外暖橘 + 中纸白 halo + 内暖橘，14px 直径） */}
          <div
            className="absolute"
            style={{
              left: `${markerLeftPct}%`,
              top: 'calc(2.25rem + 5px)',  // 色条垂直中心（h-2.5=10px 的一半）
              transform: 'translate(-50%, -50%)',
              width: '14px',
              height: '14px',
            }}
          >
            <div className="absolute inset-0 rounded-full bg-accent" />
            <div className="absolute inset-[3px] rounded-full bg-paper-card shadow-sm" />
            <div className="absolute inset-[5px] rounded-full bg-accent" />
          </div>

          {/* 价格标签：在线顶端（容器顶部） */}
          <div
            className="absolute text-center whitespace-nowrap"
            style={{
              left: `${markerLeftPct}%`,
              top: 0,
              transform: 'translateX(-50%)',
            }}
          >
            <div className="text-accent font-mono font-bold text-xs">¥{fmtPrice(currentPrice)}</div>
            <div className="text-accent-hover font-mono text-[10px] opacity-80">
              {currentPE != null ? `PE ${currentPE.toFixed(1)}` : 'PE -'}
              {' / '}
              {currentPB != null ? `PB ${currentPB.toFixed(2)}` : 'PB -'}
            </div>
          </div>
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
          // 顶头/顶尾的 tick 标签 clamp 到 [4%, 96%]，避免被卡片边界截掉一半
          const tickLeftPct = Math.max(4, Math.min(96, pct(p.price)));
          const tickLevel = levels[p.key];
          const tickPE = tickLevel?.pe ?? null;
          const tickPB = tickLevel?.pb ?? null;
          return (
            <div
              key={p.key}
              className="absolute -translate-x-1/2 text-center"
              style={{ left: `${tickLeftPct}%` }}
            >
              <span className={`inline-block text-[10px] px-1.5 py-0.5 rounded font-semibold border ${tagClass}`}>
                {meta.tag}
              </span>
              <div className="text-ink font-mono font-semibold text-xs mt-0.5">¥{fmtPrice(p.price)}</div>
              <div className="text-ink-muted font-mono text-[9px]">
                {tickPE != null ? `PE ${tickPE.toFixed(1)}` : 'PE -'}
                {' / '}
                {tickPB != null ? `PB ${tickPB.toFixed(2)}` : 'PB -'}
              </div>
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