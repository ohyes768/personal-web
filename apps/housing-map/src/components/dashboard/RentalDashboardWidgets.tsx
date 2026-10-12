'use client';

import type { RentalAreaBand, RentalBedroomsFilter, RentalSummaryEntry } from '../../lib/rental-types';
import { formatSampleCountCell, formatUnitRentCell, formatYieldCell } from '../../lib/rental-dashboard';

export interface RentalScope {
  areaBand: RentalAreaBand;
  bedrooms: RentalBedroomsFilter;
}

const AREA_BAND_OPTIONS: ReadonlyArray<readonly [RentalAreaBand, string]> = [
  ['lt90', '90㎡以下'],
  ['90to144', '90–144㎡'],
  ['gte144', '144㎡及以上'],
  ['all', '全部面积'],
];

const BEDROOMS_OPTIONS: ReadonlyArray<readonly [RentalBedroomsFilter, string]> = [
  ['all', '全部房型'],
  ['1', '1居'],
  ['2', '2居'],
  ['3', '3居'],
  ['4plus', '4居及以上'],
];

/**
 * 看板全局租金口径选择器：面积段 + 房型。
 * 三列与排序都基于该口径，绝不隐式任选最高收益组；切换口径由调用方重置排序键。
 */
export function RentalScopeSelect({ scope, onChange }: {
  scope: RentalScope;
  onChange: (next: RentalScope) => void;
}) {
  return <>
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
      租金面积段
      <select
        className="select-input"
        value={scope.areaBand}
        onChange={e => onChange({ ...scope, areaBand: e.target.value as RentalAreaBand })}
      >
        {AREA_BAND_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
    <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
      租金房型
      <select
        className="select-input"
        value={scope.bedrooms}
        onChange={e => onChange({ ...scope, bedrooms: e.target.value as RentalBedroomsFilter })}
      >
        {BEDROOMS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  </>;
}

/**
 * 看板表格租金三列：租金单价（元/㎡/月）、参考年化收益率、有效样本数。
 * 缺失一律显示 '—'；收益率带"参考"标识提示粗略估算口径。
 */
export function RentalSummaryCells({ summary }: { summary: RentalSummaryEntry | undefined }) {
  const yieldPct = summary?.annualized_gross_yield_pct;
  return <>
    <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
      {formatUnitRentCell(summary?.unit_rent_yuan_m2_month)}
    </td>
    <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
      {formatYieldCell(yieldPct)}
      {yieldPct != null && (
        <span
          title="参考年化毛收益率：单位租金×12÷售价单价，粗略估算；小区均价与租金组并非同户型成交，仅供数量级参考"
          style={{
            marginLeft: '4px', fontSize: '10px', padding: '1px 4px', borderRadius: '3px',
            background: 'var(--bg-primary)', color: 'var(--text-muted)',
          }}
        >
          参考
        </span>
      )}
    </td>
    <td style={{ color: 'var(--text-muted)' }}>{formatSampleCountCell(summary?.sample_count)}</td>
  </>;
}
