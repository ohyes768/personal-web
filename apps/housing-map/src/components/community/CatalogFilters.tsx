'use client';

import type { ChangeEvent, ReactNode } from 'react';
import { positionBucketLabels } from './PositionPanel';
import { useReviewFilterLabels } from './UseReviewPanel';

export type CatalogFilterKey = 'q' | 'district' | 'position' | 'market' | 'property_type' | 'use' | 'operation';
export type CatalogFilterValues = Record<CatalogFilterKey, string>;

export const emptyCatalogFilters = (): CatalogFilterValues =>
  ({ q: '', district: '', position: '', market: '', property_type: '', use: '', operation: '' });

export const catalogFilterLabels: Record<CatalogFilterKey, string> = {
  q: '搜索', district: '区域', position: '定位状态', market: '房源类型',
  property_type: '来源用途', use: '住宅用途核对', operation: '待处理操作',
};

/** 每个目录页签适用哪些条件：请求参数、生效摘要与可见控件共用这一份定义。 */
const scopes: Record<string, { primary: CatalogFilterKey[]; more: CatalogFilterKey[] }> = {
  admitted: { primary: ['q', 'district', 'market', 'position', 'use'], more: [] },
  pending: { primary: ['q', 'district', 'operation', 'use'], more: [] },
  excluded: { primary: ['q', 'district', 'property_type', 'use'], more: [] },
  auctions: { primary: ['q'], more: [] },
};

export function catalogFilterScope(mode: string) {
  return scopes[mode] || { primary: ['q'] as CatalogFilterKey[], more: [] as CatalogFilterKey[] };
}

export function catalogFilterOptions(key: CatalogFilterKey, propertyTypes: string[] = [], current = ''): { value: string; label: string }[] {
  switch (key) {
    case 'district':
      return [{ value: '', label: '全部区域' }, { value: '滨江', label: '滨江区' }, { value: '萧山', label: '萧山接壤目录' }];
    case 'market':
      return [{ value: '', label: '全部房源类型' }, { value: 'new_house', label: '新房' }, { value: 'second_hand', label: '二手房' }];
    case 'property_type': {
      const options = [...new Set(['住宅', '其他', '写字楼', ...propertyTypes, ...(current && current !== '__missing__' ? [current] : [])])];
      return [{ value: '', label: '全部来源用途' }, ...options.map(value => ({ value, label: value })), { value: '__missing__', label: '用途资料缺失' }];
    }
    case 'position':
      return [{ value: '', label: '全部定位状态' }, ...Object.entries(positionBucketLabels).map(([value, label]) => ({ value, label }))];
    case 'operation':
      return [{ value: '', label: '全部待处理操作' }, { value: 'position', label: '地点待处理' }, { value: 'use', label: '用途待确认' }, { value: 'facts', label: '资料待补' }];
    case 'use':
      return [{ value: '', label: '全部' }, ...Object.entries(useReviewFilterLabels).map(([value, label]) => ({ value, label }))];
    default:
      return [];
  }
}

/** 当前页真正发往服务端的条件；隐藏条件不参与，避免看不见的条件仍在影响结果。 */
export function catalogFilterParams(mode: string, values: CatalogFilterValues): Record<string, string> {
  const scope = catalogFilterScope(mode);
  const params: Record<string, string> = {};
  for (const key of [...scope.primary, ...scope.more]) {
    if (values[key]) params[key] = values[key];
  }
  return params;
}

export type CatalogFilterSummaryItem = { key: CatalogFilterKey; label: string; value: string };

/** 生效摘要只列出实际发往当前页的条件；数量取自同一份参数定义。 */
export function catalogFilterSummary(mode: string, values: CatalogFilterValues, propertyTypes: string[] = []): CatalogFilterSummaryItem[] {
  const params = catalogFilterParams(mode, values);
  return (Object.keys(params) as CatalogFilterKey[]).map(key => ({
    key,
    label: catalogFilterLabels[key],
    value: catalogFilterOptions(key, propertyTypes, values[key]).find(option => option.value === values[key])?.label || values[key],
  }));
}

/** 切换页签时保留搜索与区域，并清掉页签专属的筛选条件。 */
export function catalogFiltersForMode(values: CatalogFilterValues): CatalogFilterValues {
  const next = emptyCatalogFilters();
  next.q = values.q;
  next.district = values.district;
  return next;
}

export default function CatalogFilters({ mode, values, propertyTypes, total, loading, onChange, onRemove, onClear, onRefresh, extra }: {
  mode: string; values: CatalogFilterValues; propertyTypes?: string[]; total: number; loading: boolean;
  onChange: (key: CatalogFilterKey, value: string) => void;
  onRemove: (key: CatalogFilterKey) => void;
  onClear: () => void;
  onRefresh: () => void;
  extra?: ReactNode;
}) {
  const scope = catalogFilterScope(mode);
  const summary = catalogFilterSummary(mode, values, propertyTypes);
  const select = (key: CatalogFilterKey) => (event: ChangeEvent<HTMLSelectElement>) => onChange(key, event.target.value);
  return <>
    <div className="directory-toolbar catalog-toolbar">
      {scope.primary.includes('q') && <label className="directory-filter-field directory-filter-search">
        <span>搜索</span>
        <input value={values.q} placeholder="搜索小区名称、地址" onChange={event => onChange('q', event.target.value)} />
      </label>}
      {scope.primary.filter(key => key !== 'q').map(key => <label key={key} className="directory-filter-field">
        <span>{catalogFilterLabels[key]}</span>
        <select value={values[key]} onChange={select(key)}>
          {catalogFilterOptions(key, propertyTypes, values[key]).map(option =>
            <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>)}
      {extra}
      <button type="button" className="btn btn-secondary directory-refresh" aria-label="刷新名单" title="刷新名单" onClick={onRefresh}>↻</button>
    </div>
    <div className="directory-filter-summary">
      <span className="directory-filter-count">{loading ? '更新中…' : `共 ${total} 条`}</span>
      {summary.map(item => <span key={item.key} className="directory-filter-chip">
        {item.label}：{item.value}
        <button type="button" aria-label={`移除${item.label}筛选`} onClick={() => onRemove(item.key)}>×</button>
      </span>)}
      {summary.length > 0 && <button type="button" className="btn btn-secondary" onClick={onClear}>清空筛选</button>}
    </div>
  </>;
}
