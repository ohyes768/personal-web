/**
 * 顶部筛选 chip：显示已选条件，点 × 移除
 *
 * 老 tab（bond / stock）：只显示 numeric + exclude_qdii
 * market tab：加 market_types 多选 chip（每个类型单独一个 ×）
 * 代码搜索态（11-16）：额外一枚「代码 002910 ×」chip，点 × 退出搜索回到原筛选列表
 */
'use client';

import { XMarkIcon, FunnelIcon } from '@heroicons/react/24/outline';

import type { FundFilters } from '@/lib/types';
import type { FilterKey, NumericFilterKey } from '@/lib/useFilters';
import { FundCodeSearch } from './FundCodeSearch';

interface FilterChipBarProps {
  filters: Pick<FundFilters, NumericFilterKey | 'exclude_qdii' | 'market_types'>;
  onRemove: (key: FilterKey, value?: string) => void;
  /** 是否显示基金代码搜索框（右侧，与经理页搜索框同位置；仅四个基金 tab） */
  showCodeSearch?: boolean;
  /** 当前代码搜索态（6 位代码）；null/缺省 = 未搜索 */
  searchCode?: string | null;
  /** 退出代码搜索态（点 chip 的 ×） */
  onClearSearch?: () => void;
  /** 粗类别 → 展示文案（债基侧 value≠label，如 '混合型' → '混合债基'）；缺省 = 原样显示 */
  marketTypeLabels?: Record<string, string>;
}

const LABELS: Record<NumericFilterKey, { label: string; fmt: (v: number) => string }> = {
  min_age: { label: '成立年限', fmt: v => `≥ ${v} 年` },
  min_size_yi: { label: '规模', fmt: v => `≥ ${v} 亿` },
  max_dd_3y: { label: '近3年回撤', fmt: v => `≤ ${v}%` },
  min_mgr_exp: { label: '经理从业', fmt: v => `≥ ${v} 年` },
  min_sharpe: { label: '夏普', fmt: v => `≥ ${v}` },
};

const NUMERIC_KEYS = Object.keys(LABELS) as NumericFilterKey[];

export function FilterChipBar({
  filters, onRemove, showCodeSearch = false, searchCode = null, onClearSearch,
  marketTypeLabels,
}: FilterChipBarProps) {
  const activeNumeric = NUMERIC_KEYS.filter(k => filters[k] !== null);
  const marketTypes = filters.market_types ?? [];
  const hasQdii = filters.exclude_qdii;
  const searching = Boolean(searchCode);

  // ⚠ 单一返回结构：搜索框在任何筛选状态下都处在同一个 DOM 位置。
  // 曾经用「无筛选/有筛选」两个 return 分支，切换时输入框被卸载重建，
  // 正在输入的代码与焦点会丢失（表现为「搜索时前端崩溃」）。
  const hasAnyFilter =
    activeNumeric.length > 0 || hasQdii || marketTypes.length > 0;

  return (
    <div className="flex items-center gap-2 flex-wrap py-1.5">
      {searching && (
        <span className="inline-flex items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-xs text-accent">
          代码搜索 <span className="tnum font-mono font-medium">{searchCode}</span>
          <button
            onClick={() => onClearSearch?.()}
            className="hover:text-down"
            aria-label="退出代码搜索，回到筛选列表"
          >
            <XMarkIcon className="w-3 h-3" />
          </button>
        </span>
      )}
      {!hasAnyFilter && !searching && (
        <>
          <FunnelIcon className="w-3.5 h-3.5 text-ink-soft" />
          <span className="text-xs text-ink-soft">未筛选</span>
        </>
      )}
      {activeNumeric.map(key => {
        const v = filters[key] as number;
        const meta = LABELS[key];
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info"
          >
            {meta.label} {meta.fmt(v)}
            <button
              onClick={() => onRemove(key)}
              className="hover:text-down"
              aria-label={`移除${meta.label}筛选`}
            >
              <XMarkIcon className="w-3 h-3" />
            </button>
          </span>
        );
      })}
      {marketTypes.map(t => (
        <span
          key={t}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info"
        >
          基金类型: {marketTypeLabels?.[t] ?? t}
          <button
            onClick={() => onRemove('market_types', t)}
            className="hover:text-down"
            aria-label={`移除基金类型 ${marketTypeLabels?.[t] ?? t}`}
          >
            <XMarkIcon className="w-3 h-3" />
          </button>
        </span>
      ))}
      {hasQdii && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-info-tint text-info">
          排除 QDII
          <button
            onClick={() => onRemove('exclude_qdii')}
            className="hover:text-down"
            aria-label="移除排除 QDII"
          >
            <XMarkIcon className="w-3 h-3" />
          </button>
        </span>
      )}
      {showCodeSearch && <FundCodeSearch className="ml-auto" compact />}
    </div>
  );
}
