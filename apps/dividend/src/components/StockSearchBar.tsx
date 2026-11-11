/**
 * 「全部」页股票搜索条
 *
 * 只负责输入与状态提示；搜索语义（覆盖完整收集池、忽略阈值）
 * 全部在后端 /api/dividend/stocks?search= 里实现。
 */
'use client';

import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';

export interface StockSearchBarProps {
  /** 输入框内容 */
  value: string;
  /** 输入变化回调 */
  onChange: (value: string) => void;
  /** 状态提示（搜索范围 / 命中数 / 错误） */
  status?: React.ReactNode;
  /** 搜索进行中 */
  loading?: boolean;
  /** 外层容器类名 */
  className?: string;
}

export function StockSearchBar({
  value,
  onChange,
  status,
  loading,
  className = '',
}: StockSearchBarProps) {
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 ${className}`}>
      <div className="relative flex-1 min-w-[220px]">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-muted pointer-events-none" />
        <input
          type="text"
          role="searchbox"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="搜索股票名称或代码（如 美的 / 000333）"
          aria-label="搜索股票名称或代码"
          className="w-full bg-paper text-ink border border-rule-strong rounded pl-9 pr-9 py-1.5 text-sm focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-colors"
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange('')}
            aria-label="清除搜索"
            title="清除搜索"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-strong transition-colors"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        )}
      </div>
      {status && (
        <span className="text-xs text-ink-muted" role="status" aria-live="polite">
          {status}
        </span>
      )}
      {loading && <span className="text-xs text-ink-muted animate-pulse">搜索中…</span>}
    </div>
  );
}
