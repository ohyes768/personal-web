/**
 * AlertLevelBarMini — Modal 内的实时命中预览
 *
 * 与 AlertLevelBar 共享归一化逻辑：
 *   - N 个 ▲ 标记（N = 已设置的档数，2-4）
 *   - N+1 段色条（动态按相邻档的买/卖方向着色）
 *   - 不画当前价 ▲（Modal 场景：用户在设置时还没有"现价"概念）
 *   - 不画距离行、不画 L1 头部——极简预览
 */

'use client';

import { useMemo } from 'react';
import type { AlertLevels } from '@/lib/types';

export interface AlertLevelBarMiniProps {
  levels: AlertLevels;
}

type LevelKey = 'heavy_position' | 'add_position' | 'reduce_position' | 'full_exit';
type SegmentKey = 'heavy' | 'add' | 'hold' | 'reduce' | 'full';

const LEVEL_TAG: Record<LevelKey, { label: string; color: string }> = {
  heavy_position:  { label: '重仓', color: '#5A9472' },
  add_position:    { label: '加仓', color: '#C9951F' },
  reduce_position: { label: '减仓', color: '#B85C38' },
  full_exit:       { label: '全卖', color: '#A8453A' },
};

// 5 段色板（与 AlertLevelBar SEG_COLORS 对齐）
const SEG_COLORS: Record<SegmentKey, string> = {
  heavy:  '#5A9472',
  add:    '#C9951F',
  hold:   '#D9D2C2', // 中性灰（持有区）
  reduce: '#B85C38',
  full:   '#A8453A',
};

// 段位语义判定：与 AlertLevelBar gapColor 一致
// - 边界段（首/尾）：用单边档位的色
// - 中间段：两档同买→用右档色；同卖→用左档色；买→卖→持有
function gapColor(
  leftKey: LevelKey | null,
  rightKey: LevelKey | null
): SegmentKey {
  const keyToSeg = (k: LevelKey): SegmentKey => {
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

export function AlertLevelBarMini({ levels }: AlertLevelBarMiniProps) {
  const points = useMemo(() => {
    const list: Array<{ key: LevelKey; price: number }> = [];
    (Object.keys(LEVEL_TAG) as LevelKey[]).forEach(k => {
      const lv = levels[k];
      if (lv && lv.price > 0) {
        list.push({ key: k, price: lv.price });
      }
    });
    return list.sort((a, b) => a.price - b.price);
  }, [levels]);

  if (points.length < 2) {
    return (
      <div className="h-6 flex items-center justify-center text-[11px] text-ink-muted">
        填写至少 2 档价格即可预览色块分布
      </div>
    );
  }

  // Mini 没有 currentPrice，但同样只用已设置档位的价格作区间，避免首/末段被压成 0
  const minP = points[0].price;
  const maxP = points[points.length - 1].price;
  const range = maxP - minP || 1;
  const pct = (p: number) => Math.max(2, Math.min(98, ((p - minP) / range) * 100));

  // 动态生成色段：N+1 段（N = 已设置的档数，2-4）
  const segments: Array<{ key: string; left: number; width: number; color: string }> = [];
  // 首段：[0, p0]
  segments.push({
    key: `seg-0-${points[0].key}`,
    left: 0,
    width: pct(points[0].price),
    color: SEG_COLORS[gapColor(null, points[0].key)],
  });
  // 中间段
  for (let i = 0; i < points.length - 1; i++) {
    const leftPct = pct(points[i].price);
    const rightPct = pct(points[i + 1].price);
    const width = rightPct - leftPct;
    if (width <= 0) continue;
    segments.push({
      key: `seg-${i + 1}-${points[i].key}-${points[i + 1].key}`,
      left: leftPct,
      width,
      color: SEG_COLORS[gapColor(points[i].key, points[i + 1].key)],
    });
  }
  // 末段：[pn, max]
  const lastPct = pct(points[points.length - 1].price);
  const lastWidth = 100 - lastPct;
  if (lastWidth > 0) {
    segments.push({
      key: `seg-end-${points[points.length - 1].key}`,
      left: lastPct,
      width: lastWidth,
      color: SEG_COLORS[gapColor(points[points.length - 1].key, null)],
    });
  }

  return (
    <div className="relative h-6">
      {/* 动态色条 */}
      <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-2 bg-paper-deep rounded-full overflow-hidden">
        {segments.map(seg => (
          <div
            key={seg.key}
            className="absolute top-0 bottom-0"
            style={{ left: `${seg.left}%`, width: `${seg.width}%`, backgroundColor: seg.color }}
          />
        ))}
      </div>

      {/* N 个 ▲ 标记 */}
      {points.map(p => {
        const left = Math.max(4, Math.min(96, pct(p.price)));
        const color = LEVEL_TAG[p.key].color;
        return (
          <div
            key={p.key}
            className="absolute top-0 bottom-0 transform -translate-x-1/2 flex flex-col items-center justify-center"
            style={{ left: `${left}%` }}
          >
            <div className="text-xs leading-none" style={{ color }}>
              ▲
            </div>
            <div className="font-mono text-[10px] mt-0.5 whitespace-nowrap" style={{ color }}>
              ¥{p.price.toFixed(2)}
            </div>
          </div>
        );
      })}
    </div>
  );
}