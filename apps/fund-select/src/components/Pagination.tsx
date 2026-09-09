/**
 * 分页器组件（基金筛选 4 tab 通用）
 *
 * - 居中显示「第 X-Y 条 / 共 N 条」+ 「第 X / M 页」
 * - 上一页 / 下一页 按钮（边界禁用）
 * - 每页条数下拉：25 / 50 / 100
 * - `total <= limit` 时整组件不渲染（单页时完全隐藏）
 * - 数字用 `tnum`（tabular-nums）保证对齐
 */
'use client';

import { LIMIT_OPTIONS } from '@/lib/types';

interface PaginationProps {
  page: number;          // 当前 1-indexed
  limit: number;         // 当前每页条数
  total: number;         // 总命中数（与 page/limit 无关）
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
}

export function Pagination({ page, limit, total, onPageChange, onLimitChange }: PaginationProps) {
  // 单页时不渲染（调用方也可省）
  if (total <= limit) return null;

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = (page - 1) * limit + 1;
  const end = Math.min(page * limit, total);
  const atFirst = page <= 1;
  const atLast = page >= totalPages;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-3 py-3 text-xs border-t border-rule">
      <div className="text-ink-muted">
        第 <span className="tnum">{start}</span>–
        <span className="tnum">{end}</span> 条 / 共 <span className="tnum">{total}</span> 条
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={atFirst}
          aria-label="上一页"
          className="inline-flex items-center px-2.5 py-1 rounded border border-rule bg-paper-card text-ink-muted hover:text-ink-strong hover:bg-paper-deep disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          上一页
        </button>
        <span className="text-ink-muted">
          第 <span className="tnum">{page}</span> / <span className="tnum">{totalPages}</span> 页
        </span>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={atLast}
          aria-label="下一页"
          className="inline-flex items-center px-2.5 py-1 rounded border border-rule bg-paper-card text-ink-muted hover:text-ink-strong hover:bg-paper-deep disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          下一页
        </button>
      </div>
      <label className="flex items-center gap-1.5 text-ink-muted">
        每页
        <select
          value={limit}
          onChange={e => onLimitChange(Number(e.target.value))}
          aria-label="每页条数"
          className="px-1.5 py-1 rounded border border-rule bg-paper-card text-ink-strong text-xs"
        >
          {LIMIT_OPTIONS.map(n => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        条
      </label>
    </div>
  );
}