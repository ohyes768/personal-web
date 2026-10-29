'use client';

// 地图上的房源类型切换: 二手房 / 新房 / 全部。
// 计数按当前可见集合(名称、区域、物业类型等筛选之后)统计, 与地图上实际画出来的对象一致。

import { MARKET_MODE_OPTIONS, type MarketMode } from '@/lib/market-map';

export interface MarketModeCounts {
  visible: number;      // 当前可见总数
  second_hand: number;
  new_house: number;
  unknown: number;      // 房源类型待核实
}

interface MarketModeFilterProps {
  mode: MarketMode;
  counts: MarketModeCounts;
  onChange: (mode: MarketMode) => void;
}

export default function MarketModeFilter({ mode, counts, onChange }: MarketModeFilterProps) {
  return (
    <div>
      <div style={{ display: 'flex', gap: '6px' }} role="group" aria-label="房源类型">
        {MARKET_MODE_OPTIONS.map(option => (
          <button
            key={option.value}
            className={`poi-toggle ${mode === option.value ? 'active' : ''}`}
            style={{ padding: '4px 10px', fontSize: '12px' }}
            aria-pressed={mode === option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '6px', lineHeight: 1.6 }}>
        当前可见 {counts.visible} 个 · 二手房 {counts.second_hand} · 新房 {counts.new_house}
        {counts.unknown > 0 && <> · 房源类型待核实 {counts.unknown}</>}
      </div>
      {mode !== 'all' && counts.unknown > 0 && (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
          房源类型待核实的小区只在「全部」里出现
        </div>
      )}
    </div>
  );
}
