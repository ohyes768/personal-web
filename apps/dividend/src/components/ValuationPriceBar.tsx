/**
 * ValuationPriceBar — 收藏跟踪价格条（四阈值五区间）
 *
 * 职责单一：回答「现价在我的四条价格线之间处于什么位置」。
 * 精简后的三层结构（2026-11-11 distill）：
 *   行1 四档价签 + 现价签（相邻过近时错层）
 *   行2 五区间色条 + 四圆点（点击看该价位股息率）+ 现价标记
 *   行3 区间名（当前所在段高亮）
 *
 * 移出的信息一律走渐进披露，不再占高度：
 * - 每档 PE/PB → 报告面板四价卡片已有；条上悬浮 tooltip 也带
 * - 距各档距离百分比 → 条上位置已表达同一事实，精确数字留在 tooltip
 * - 「当前所在区」文字块 → 行3 的高亮已表达，不再重复一遍
 * - 生效态的卡片边框/底色 → 表格行已分格，去掉嵌套卡片；候选态保留虚线框，
 *   那是「尚未启用监控」的语义信号，不是装饰
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
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
  currentPE?: number | null;
  currentPB?: number | null;
  /** 2025 年每股分红（元），用于点击点位看股息率 */
  dividend2025?: number | null;
  /** 实时股息率 TTM（%），仅现价点展示 */
  yieldTtm?: number | null;
  variant?: ValuationBarVariant;
  title?: string;
  /** 覆盖默认宽度（用于对比预览或不同列宽） */
  style?: React.CSSProperties;
}

interface ThresholdPoint {
  key: ValuationLevelKey;
  price: number;
  pe: number | null;
  pb: number | null;
}

type YieldKey = ValuationLevelKey | 'current';

/** 价位映射到 [8, 92]，两侧留出价签安全边距（避免贴边裁切） */
function pctOf(price: number, min: number, max: number): number {
  if (max <= min) return 50;
  return 8 + ((price - min) / (max - min)) * 84;
}

/** 标签过近时上下错层：0=上层 / 1=下层 */
function staggerRows(lefts: number[], minGap: number): number[] {
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

function fmtPrice(p: number): string {
  return p.toFixed(2);
}

function fmtPct(p: number): string {
  const sign = p > 0 ? '+' : '';
  return `${sign}${p.toFixed(1)}%`;
}

function calcYieldAtPrice(dividend: number | null | undefined, price: number): number | null {
  if (dividend == null || dividend <= 0 || price <= 0) return null;
  return (dividend / price) * 100;
}

export function ValuationPriceBar({
  levels,
  currentPrice,
  currentPE,
  currentPB,
  dividend2025,
  yieldTtm,
  variant = 'effective',
  title,
  style,
}: ValuationPriceBarProps) {
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
      if (e.target instanceof Node && !el.contains(e.target)) setOpenYield(null);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [openYield]);

  const points = useMemo<ThresholdPoint[]>(() => {
    const list: ThresholdPoint[] = [];
    VALUATION_LEVEL_KEYS.forEach(key => {
      const lv = levels[key];
      if (lv && lv.price > 0) {
        list.push({ key, price: lv.price, pe: lv.pe ?? null, pb: lv.pb ?? null });
      }
    });
    list.sort((a, b) => a.price - b.price);
    return list;
  }, [levels]);

  // 不足两条价格线不画条（不画虚构五块）
  if (points.length < 2) return null;

  const minP = points[0].price;
  const maxP = points[points.length - 1].price;
  const pct = (p: number) => pctOf(p, minP, maxP);

  // 五区间：<重仓 / 重仓~加仓 / 加仓~减仓 / 减仓~全卖 / >全卖
  const segments = [{ side: 'heavy', left: 0, width: pct(points[0].price) }];
  for (let i = 0; i < points.length - 1; i++) {
    const left = pct(points[i].price);
    const right = pct(points[i + 1].price);
    const side = i === 0 ? 'add' : i === 1 ? 'hold' : 'reduce';
    segments.push({ side, left, width: Math.max(right - left, 0.5) });
  }
  segments.push({ side: 'full', left: pct(maxP), width: 100 - pct(maxP) });

  const hasPrice = currentPrice != null && currentPrice > 0;
  const belowAll = hasPrice && currentPrice < minP;
  const aboveAll = hasPrice && currentPrice > maxP;
  const markerPct = !hasPrice ? null : belowAll ? 8 : aboveAll ? 92 : pct(currentPrice);

  const currentSegSide = !hasPrice
    ? null
    : currentPrice <= points[0].price ? 'heavy'
      : currentPrice <= points[1].price ? 'add'
        : currentPrice <= points[2].price ? 'hold'
          : currentPrice <= points[3].price ? 'reduce'
            : 'full';

  // 价签错层：四档价签 + 现价一起算（现价也占位，避免与档位价签重叠）
  const labelLefts = [
    ...points.map(p => Math.max(6, Math.min(94, pct(p.price)))),
    ...(hasPrice && markerPct !== null ? [Math.max(6, Math.min(94, markerPct))] : []),
  ];
  const labelRows = staggerRows(labelLefts, 12);
  const levelRows = labelRows.slice(0, points.length);
  const currentRow = labelRows[labelRows.length - 1] ?? 0;

  const fmtPePb = (pe: number | null | undefined, pb: number | null | undefined): string | null => {
    const parts: string[] = [];
    if (pe != null) parts.push(`PE ${pe.toFixed(1)}`);
    if (pb != null) parts.push(`PB ${pb.toFixed(2)}`);
    return parts.length > 0 ? parts.join(' · ') : null;
  };

  // 悬浮 tooltip 承载被移出的细节：每档 PE/PB 与距各档距离
  const detailTitle = (() => {
    const lines: string[] = [];
    if (title) lines.push(title);
    lines.push(points.map(p => {
      const pePb = fmtPePb(p.pe, p.pb);
      const dist = hasPrice && p.price > 0 ? `距 ${fmtPct(((currentPrice - p.price) / p.price) * 100)}` : '';
      return `${VALUATION_LEVEL_LABEL[p.key]} ¥${fmtPrice(p.price)}${pePb ? ` · ${pePb}` : ''}${dist ? ` · ${dist}` : ''}`;
    }).join('　'));
    if (hasPrice) {
      lines.push(`现价 ¥${fmtPrice(currentPrice)}${fmtPePb(currentPE, currentPB) ? ` · ${fmtPePb(currentPE, currentPB)}` : ''}${currentSegSide ? ` · ${SEG_LABELS[currentSegSide]}` : ''}`);
    } else {
      lines.push('现价缺失');
    }
    return lines.join('\n');
  })();

  return (
    <div
      ref={rootRef}
      className="relative w-[400px] max-w-full"
      style={style}
      title={detailTitle}
      data-testid={`valuation-bar-${variant}`}
    >
      {/* 行1 价签 + 行2 色条 */}
      <div className="relative h-[46px]">
        {/* 行1 四档价签（候选态用弱化色，避免与已生效挡位混淆） */}
        {points.map((p, idx) => {
          const left = Math.max(6, Math.min(94, pct(p.price)));
          const row = levelRows[idx] ?? 0;
          return (
            <div
              key={p.key}
              className={`absolute left-0 -translate-x-1/2 whitespace-nowrap font-mono font-semibold text-[11px] tabular-nums pointer-events-none ${
                variant === 'candidate' ? 'text-ink-muted' : 'text-ink'
              }`}
              style={{ left: `${left}%`, top: row === 0 ? 0 : '0.95rem' }}
            >
              {fmtPrice(p.price)}
            </div>
          );
        })}
        {/* 行1 现价签 */}
        {hasPrice && markerPct !== null && (
          <div
            className="absolute left-0 -translate-x-1/2 whitespace-nowrap text-accent font-mono font-bold text-xs tabular-nums drop-shadow-sm pointer-events-none"
            style={{ left: `${Math.max(6, Math.min(94, markerPct))}%`, top: currentRow === 0 ? '0.05rem' : '1rem' }}
          >
            {belowAll ? '↓ ' : aboveAll ? '↑ ' : ''}¥{fmtPrice(currentPrice)}
          </div>
        )}

        {/* 行2 五区间色条（候选态整体弱化） */}
        <div className="absolute left-0 right-0 top-[30px] h-2.5 bg-paper-deep rounded-full overflow-hidden">
          {segments.map((seg, i) => (
            <div
              key={`${seg.side}-${i}`}
              className="absolute top-0 bottom-0"
              style={{
                left: `${seg.left}%`, width: `${seg.width}%`,
                backgroundColor: SEG_COLORS[seg.side],
                opacity: variant === 'candidate' ? 0.55 : 1,
              }}
            />
          ))}
        </div>

        {/* 行2 四圆点（点击看该价位股息率） */}
        {points.map((p) => {
          const left = Math.max(6, Math.min(94, pct(p.price)));
          const isOpen = openYield === p.key;
          return (
            <div key={p.key} className="absolute inset-y-0 w-0 z-[1]" style={{ left: `${left}%` }}>
              <button
                type="button"
                title={`${VALUATION_LEVEL_LABEL[p.key]} ¥${fmtPrice(p.price)}${fmtPePb(p.pe, p.pb) ? ` · ${fmtPePb(p.pe, p.pb)}` : ''} · 点击看股息率`}
                aria-expanded={isOpen}
                aria-label={`${VALUATION_LEVEL_LABEL[p.key]} ¥${fmtPrice(p.price)}，点击看股息率`}
                className="absolute left-0 -translate-x-1/2 flex items-center justify-center w-7 h-7 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full motion-safe:hover:scale-105 motion-safe:transition-transform motion-safe:duration-200"
                style={{ top: '19px' }}
                onClick={e => {
                  e.stopPropagation();
                  setOpenYield(prev => (prev === p.key ? null : p.key));
                }}
              >
                <span
                  className="block rounded-full border-2 border-paper-card shadow-sm"
                  style={{
                    width: '8px', height: '8px',
                    backgroundColor: SEG_COLORS[p.key === 'heavy_position' ? 'heavy' : p.key === 'add_position' ? 'add' : p.key === 'reduce_position' ? 'reduce' : 'full'],
                  }}
                />
              </button>
              {isOpen && (
                <YieldPopover
                  title={`${VALUATION_LEVEL_LABEL[p.key]}档`}
                  price={p.price}
                  yieldPct={calcYieldAtPrice(dividend2025, p.price)}
                  align={popoverAlign(left)}
                  onClose={() => setOpenYield(null)}
                />
              )}
            </div>
          );
        })}

        {/* 行2 现价标记（竖线穿过色条） */}
        {hasPrice && markerPct !== null && (
          <div className="absolute inset-y-0 w-0 z-10" style={{ left: `${markerPct}%` }}>
            <div
              className="absolute left-0 -translate-x-1/2 bg-accent opacity-75 pointer-events-none"
              style={{ top: '28px', height: '14px' }}
            />
            <button
              type="button"
              title={`现价 ¥${fmtPrice(currentPrice)}${fmtPePb(currentPE, currentPB) ? ` · ${fmtPePb(currentPE, currentPB)}` : ''} · 点击看股息率`}
              aria-expanded={openYield === 'current'}
              aria-label={`现价 ¥${fmtPrice(currentPrice)}，点击看股息率`}
              className="absolute left-0 -translate-x-1/2 flex items-center justify-center w-7 h-7 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-full motion-safe:hover:scale-105 motion-safe:transition-transform motion-safe:duration-200"
              style={{ top: '19px' }}
              onClick={e => {
                e.stopPropagation();
                setOpenYield(prev => (prev === 'current' ? null : 'current'));
              }}
            >
              <span className="relative block" style={{ width: '13px', height: '13px' }}>
                <span className="absolute inset-0 rounded-full bg-accent shadow-md" />
                <span className="absolute inset-[2.5px] rounded-full bg-paper-card" />
                <span className="absolute inset-[4.5px] rounded-full bg-accent" />
              </span>
            </button>
            {openYield === 'current' && (
              <YieldPopover
                title="现价"
                price={currentPrice}
                yieldPct={calcYieldAtPrice(dividend2025, currentPrice)}
                yieldTtm={yieldTtm}
                accent
                align={popoverAlign(markerPct)}
                onClose={() => setOpenYield(null)}
              />
            )}
          </div>
        )}
      </div>

      {/* 行3 区间名：按实际占位依次排布，挤不下的不画（当前所在段高亮） */}
      <div className="relative h-[15px]">
        {(() => {
          // 区间名约占 10% 宽（3 字 + 色点），右侧预留越界/未启用提示的位置
          const LABEL_W = 10;
          let cursor = 0;
          const outOfRange = (belowAll || aboveAll);
          const reserved = variant === 'candidate' || outOfRange;
          return segments.map((seg, i) => {
            const isFirst = i === 0;
            const isLast = i === segments.length - 1;
            // 越界时该端的区间名让位给越界提示；候选态让位给「未启用」标签
            if (reserved && isLast) return null;
            if (outOfRange && isFirst) return null;
            if (!isFirst && !isLast && seg.width < 12) return null;
            const center = seg.left + seg.width / 2;
            const left = isFirst ? 0 : isLast ? 100 - LABEL_W : center - LABEL_W / 2;
            const right = left + LABEL_W;
            if (left < cursor) return null; // 与上一个名称重叠，放弃
            cursor = right;
            const isCurrent = currentSegSide === seg.side;
            return (
              <div
                key={`${seg.side}-${i}`}
                className="absolute top-0 whitespace-nowrap"
                style={{ left: `${left}%`, transform: isFirst ? 'translateX(0)' : 'translateX(-50%)' }}
              >
                <span className={`inline-flex items-center gap-1 text-[9px] ${isCurrent ? 'text-ink font-medium' : 'text-ink-muted'}`}>
                  <span
                    className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: SEG_COLORS[seg.side] }}
                    aria-hidden
                  />
                  {SEG_LABELS[seg.side]}
                </span>
              </div>
            );
          });
        })()}
        {belowAll && (
          <span className="absolute left-0 top-0 text-[9px] text-accent whitespace-nowrap">低于重仓线</span>
        )}
        {aboveAll && (
          <span className="absolute right-0 top-0 text-[9px] text-accent whitespace-nowrap">高于全卖线</span>
        )}
        {variant === 'candidate' && (
          <span
            className="absolute right-0 top-0 text-[9px] text-ink-muted whitespace-nowrap"
            title="评估结果尚未应用，监控未启用"
          >
            未启用
          </span>
        )}
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
      className={`absolute ${alignCls} top-[34px] z-20 w-max max-w-[11rem] rounded border border-rule bg-paper-card px-2.5 py-2 shadow-md`}
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
        <div className={`font-mono font-bold text-lg leading-none tabular-nums ${yieldPct >= 5 ? 'text-emerald-700' : yieldPct >= 3 ? 'text-emerald-600' : 'text-ink'}`}>
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
          <span className="font-mono font-semibold tabular-nums">{yieldTtm.toFixed(2)}%</span>
        </div>
      )}
    </div>
  );
}
