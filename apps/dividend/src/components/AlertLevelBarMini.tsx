/**
 * AlertLevelBarMini — Modal 内的实时命中预览
 *
 * 与 AlertLevelBar 共享归一化逻辑，但只画 4 个 ▲ 标记（按 4 档价格定位）
 * 不画当前价 ▲（Modal 场景：用户在设置时还没有"现价"概念）
 * 不画距离行、不画 L1 头部——极简预览
 */

'use client';

import { useMemo } from 'react';
import type { AlertLevels } from '@/lib/types';

export interface AlertLevelBarMiniProps {
  levels: AlertLevels;
}

type LevelKey = 'heavy_position' | 'add_position' | 'reduce_position' | 'full_exit';

const LEVEL_TAG: Record<LevelKey, { label: string; color: string }> = {
  heavy_position:  { label: '重仓', color: '#5A9472' },
  add_position:    { label: '加仓', color: '#C9951F' },
  reduce_position: { label: '减仓', color: '#B85C38' },
  full_exit:       { label: '全卖', color: '#A8453A' },
};

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
    // 至少 2 档才有预览意义，否则只占位提示
    return (
      <div className="h-6 flex items-center justify-center text-[11px] text-ink-muted">
        填写至少 2 档价格即可预览色块分布
      </div>
    );
  }

  const minP = points[0].price;
  const maxP = points[points.length - 1].price;
  const range = maxP - minP || 1;
  const pct = (p: number) => Math.max(2, Math.min(98, ((p - minP) / range) * 100));

  return (
    <div className="relative h-6">
      {/* 4 段色条 */}
      <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-2 bg-paper-deep rounded-full overflow-hidden">
        {points.slice(0, -1).map((p, i) => {
          const next = points[i + 1];
          const left = pct(p.price);
          const right = pct(next.price);
          const color = LEVEL_TAG[next.key].color;
          return (
            <div
              key={p.key}
              className="absolute top-0 bottom-0"
              style={{ left: `${left}%`, width: `${right - left}%`, backgroundColor: color }}
            />
          );
        })}
      </div>

      {/* 4 个 ▲ 标记 */}
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