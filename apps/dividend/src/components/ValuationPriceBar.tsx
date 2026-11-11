/**
 * ValuationPriceBar — 收藏跟踪窄价格条（四阈值五区间）
 *
 * 用户要求：比原型更窄（220–260px）、4 挡位/5 块加条、未评估不显示。
 * 语义：
 * - variant=effective：已应用生效挡位（实线边框）
 * - variant=candidate：首次 ready 尚未应用（虚线边框 + 角标「评估结果 · 未启用监控」）
 * - 现价越界（低于重仓/高于全卖）：标记贴边并显示越界方向箭头 + 文案
 * - 缺现价：不画标记，底部显示「现价缺失」
 * 无 levels 时不渲染（调用方决定占位），绝不画虚构价格。
 */
'use client';

import { useMemo } from 'react';
import type { AlertLevels } from '@/lib/types';
import { VALUATION_LEVEL_KEYS, VALUATION_LEVEL_LABEL, type ValuationLevelKey } from '@/lib/valuation';

const SEG_COLORS: Record<string, string> = {
  heavy: '#5A9472',
  add: '#C9951F',
  hold: '#D9D2C2',
  reduce: '#D4893A',
  full: '#9B2F2F',
};

const SEG_LABELS: Record<string, string> = {
  heavy: '重仓区',
  add: '加仓区',
  hold: '持有区',
  reduce: '减仓区',
  full: '全卖区',
};

export type ValuationBarVariant = 'effective' | 'candidate';

export interface ValuationPriceBarProps {
  levels: AlertLevels;
  currentPrice?: number | null;
  variant?: ValuationBarVariant;
  title?: string;
}

interface ThresholdPoint {
  key: ValuationLevelKey;
  price: number;
}

/** 位置百分比：把价格映射到 [2, 98]，留出贴边标记空间 */
function pctOf(price: number, min: number, max: number): number {
  if (max <= min) return 50;
  return 2 + ((price - min) / (max - min)) * 96;
}

export function ValuationPriceBar({ levels, currentPrice, variant = 'effective', title }: ValuationPriceBarProps) {
  const points = useMemo<ThresholdPoint[]>(() => {
    const list: ThresholdPoint[] = [];
    VALUATION_LEVEL_KEYS.forEach(key => {
      const lv = levels[key];
      if (lv && lv.price > 0) list.push({ key, price: lv.price });
    });
    list.sort((a, b) => a.price - b.price);
    return list;
  }, [levels]);

  if (points.length < 2) return null;

  const minP = points[0].price;
  const maxP = points[points.length - 1].price;
  const pct = (p: number) => pctOf(p, minP, maxP);

  // 五区间：重仓区(<重仓) / 加仓区 / 持有区 / 减仓区 / 全卖区(>全卖)
  const segments = [
    { side: 'heavy', left: 0, width: pct(points[0].price) },
  ];
  for (let i = 0; i < points.length - 1; i++) {
    const left = pct(points[i].price);
    const right = pct(points[i + 1].price);
    const side = i === 0 ? 'add' : i === 1 ? 'hold' : 'reduce';
    segments.push({ side, left, width: Math.max(right - left, 0.5) });
  }
  segments.push({ side: 'full', left: pct(maxP), width: 100 - pct(maxP) });

  // 现价状态：区间归属 + 越界方向
  const hasPrice = currentPrice != null && currentPrice > 0;
  const belowAll = hasPrice && currentPrice < minP;
  const aboveAll = hasPrice && currentPrice > maxP;
  const markerPct = !hasPrice ? null : belowAll ? 2 : aboveAll ? 98 : pct(currentPrice);

  const currentSegSide = !hasPrice
    ? null
    : currentPrice <= points[0].price ? 'heavy'
      : currentPrice <= points[1].price ? 'add'
        : currentPrice <= points[2].price ? 'hold'
          : currentPrice <= points[3].price ? 'reduce'
            : 'full';

  const fmt = (p: number) => p.toFixed(2);

  return (
    <div
      className={`relative rounded-lg px-2 pt-1.5 pb-2 w-[248px] max-w-full bg-paper-card ${
        variant === 'candidate' ? 'border border-dashed border-rule-strong' : 'border border-rule'
      }`}
      title={title}
      data-testid={`valuation-bar-${variant}`}
    >
      {variant === 'candidate' && (
        <div className="absolute -top-2 left-2 bg-paper-tint border border-rule-strong rounded px-1.5 py-px text-[9px] text-ink-muted whitespace-nowrap">
          评估结果 · 未启用监控
        </div>
      )}

      {/* 四价标签（错层避让）+ 细条 */}
      <div className="relative pt-6 pb-5">
        <div className="relative h-2.5 rounded-full overflow-hidden">
          {segments.map((seg, i) => (
            <div
              key={`${seg.side}-${i}`}
              className="absolute top-0 bottom-0"
              style={{ left: `${seg.left}%`, width: `${seg.width}%`, backgroundColor: SEG_COLORS[seg.side] }}
            />
          ))}
        </div>

        {/* 四阈值刻度：短竖线 + 价签（1/3 上层、2/4 下层，避免 248px 内重叠） */}
        {points.map((p, idx) => {
          const left = Math.max(2, Math.min(98, pct(p.price)));
          const row = idx % 2 === 0 ? 0 : 1;
          return (
            <div key={p.key} className="absolute inset-y-0 w-0 z-[1]" style={{ left: `${left}%` }}>
              <div className="absolute top-[1.7rem] h-2 w-px bg-ink-muted/60 -translate-x-1/2" />
              <div
                className="absolute -translate-x-1/2 whitespace-nowrap text-center font-mono text-[9px] text-ink-muted tabular-nums pointer-events-none"
                style={{ top: row === 0 ? '0.15rem' : '0.85rem' }}
                title={`${VALUATION_LEVEL_LABEL[p.key]}线 ¥${fmt(p.price)}`}
              >
                {fmt(p.price)}
              </div>
            </div>
          );
        })}

        {/* 现价标记 */}
        {hasPrice && markerPct !== null && (
          <div className="absolute inset-y-0 w-0 z-10" style={{ left: `${markerPct}%` }}>
            <div
              className="absolute top-[1.4rem] w-0.5 h-[1.4rem] bg-accent -translate-x-1/2 pointer-events-none"
              data-testid="valuation-current-marker"
            />
            <div
              className={`absolute -translate-x-1/2 whitespace-nowrap font-mono font-bold text-[11px] tabular-nums text-accent ${
                belowAll ? 'translate-x-[-38%]' : aboveAll ? 'translate-x-[-62%]' : ''
              }`}
              style={{ top: '3.6rem' }}
            >
              {belowAll ? '↓ ' : aboveAll ? '↑ ' : ''}¥{fmt(currentPrice)}
            </div>
          </div>
        )}

        {/* 越界提示 */}
        {belowAll && (
          <span className="absolute right-1.5 top-0 text-[9px] text-accent whitespace-nowrap">低于重仓线</span>
        )}
        {aboveAll && (
          <span className="absolute right-1.5 top-0 text-[9px] text-accent whitespace-nowrap">高于全卖线</span>
        )}

        {/* 现价所在区名（替代原型五区全标：窄条只标命中区） */}
        {hasPrice && currentSegSide && (
          <div className="absolute bottom-0 left-2 text-[9px] text-ink-muted flex items-center gap-1">
            <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: SEG_COLORS[currentSegSide] }} />
            {SEG_LABELS[currentSegSide]}
            {(belowAll || aboveAll) && <span>（越界）</span>}
          </div>
        )}
        {!hasPrice && (
          <div className="absolute bottom-0 left-2 text-[9px] text-ink-muted">现价缺失 · 暂无位置标记</div>
        )}
      </div>
    </div>
  );
}
