/**
 * 基金对比表格（泛型化维度驱动，从 dividend CompareTable 重写）
 *
 * 维度分两类：
 *  - highlight：参与最优高亮（direction: max / min / min-abs）
 *  - displayOnly：只展示不高亮（利率债占比、申购费、赎回各档）
 */
'use client';

import { useMemo } from 'react';
import { StarIcon, XMarkIcon } from '@heroicons/react/24/outline';

export type CompareDirection = 'max' | 'min' | 'min-abs';

export interface CompareDimension<T> {
  key: string;
  label: string;
  extract: (item: T) => number | null | undefined;
  format: (v: number) => string;
  direction?: CompareDirection;   // 无 = displayOnly
}

interface CompareTableProps<T> {
  items: T[];
  dimensions: Array<CompareDimension<T>>;
  onRemove: (code: string) => void;
}

/** 各高亮维度的最优索引（None 值不参与） */
function useHighlights<T extends { code: string }>(
  items: T[],
  dimensions: Array<CompareDimension<T>>
): Record<string, number> {
  return useMemo(() => {
    const result: Record<string, number> = {};
    for (const dim of dimensions) {
      if (!dim.direction) continue;
      const values = items.map(it => dim.extract(it));
      const valid = values.map((v, i) => ({ v, i })).filter(x => x.v != null);
      if (valid.length === 0) continue;

      let best = valid[0];
      for (const cand of valid) {
        const a = dim.direction === 'max' ? cand.v! : (
          dim.direction === 'min' ? cand.v! : Math.abs(cand.v!)
        );
        const b = dim.direction === 'max' ? best.v! : (
          dim.direction === 'min' ? best.v! : Math.abs(best.v!)
        );
        if (a < b || (a === b && cand.i < best.i)) best = cand;
      }
      // 唯一最优才高亮（并列不清真）
      const bestVal = dim.direction === 'min-abs' ? Math.abs(best.v!) : best.v!;
      const tieCount = valid.filter(x =>
        (dim.direction === 'min-abs' ? Math.abs(x.v!) : x.v!) === bestVal
      ).length;
      if (tieCount === 1) result[dim.key] = best.i;
    }
    return result;
  }, [items, dimensions]);
}

export function CompareTable<T extends { code: string; name: string }>({
  items, dimensions, onRemove,
}: CompareTableProps<T>) {
  const highlights = useHighlights(items, dimensions);

  if (items.length === 0) {
    return (
      <div className="text-center py-16">
        <XMarkIcon className="w-16 h-16 mx-auto text-gray-600 mb-4" />
        <h3 className="text-lg font-semibold text-gray-400 mb-2">暂无对比数据</h3>
        <p className="text-sm text-gray-500">请从列表中选择 2-5 只基金进行对比</p>
      </div>
    );
  }

  const highlightDims = dimensions.filter(d => d.direction);
  const displayDims = dimensions.filter(d => !d.direction);

  const renderRow = (dim: CompareDimension<T>) => (
    <tr key={dim.key} className="hover:bg-paper-tint">
      <td className="px-4 py-2 text-gray-300 border-b border-gray-700">
        <span>{dim.label}</span>
      </td>
      {items.map((item, idx) => {
        const v = dim.extract(item);
        const isBest = highlights[dim.key] === idx;
        return (
          <td key={item.code} className="px-4 py-2 text-center border-b border-gray-700">
            {v != null ? (
              isBest ? (
                <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/20 text-green-400 rounded">
                  <StarIcon className="w-4 h-4 text-yellow-400" aria-label="最优值" />
                  <span className="font-mono tnum">{dim.format(v)}</span>
                </span>
              ) : (
                <span className="font-mono tnum">{dim.format(v)}</span>
              )
            ) : (
              <span>-</span>
            )}
          </td>
        );
      })}
    </tr>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-800 sticky top-0 z-10">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider min-w-[100px] w-[100px]">
              维度
            </th>
            {items.map(item => (
              <th key={item.code} className="px-4 py-3 text-center min-w-[120px]">
                <div className="flex items-center justify-center gap-2">
                  <div className="font-medium text-gray-200">{item.name}</div>
                  <button
                    onClick={() => onRemove(item.code)}
                    className="flex items-center gap-1 px-2 py-0.5 text-xs text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded transition-colors"
                    aria-label={`移除 ${item.name}`}
                  >
                    <XMarkIcon className="w-4 h-4" />
                    <span>移除</span>
                  </button>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="hover:bg-paper-tint">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">代码</td>
            {items.map(item => (
              <td key={item.code} className="px-4 py-2 text-center text-gray-300 font-mono border-b border-gray-700">
                {item.code}
              </td>
            ))}
          </tr>
          <tr className="hover:bg-paper-tint">
            <td className="px-4 py-2 text-gray-300 border-b border-gray-700">公司</td>
            {items.map(item => (
              <td key={item.code} className="px-4 py-2 text-center text-gray-300 border-b border-gray-700 text-xs">
                {(item as { mgr_company?: string | null }).mgr_company || '-'}
              </td>
            ))}
          </tr>
          {highlightDims.map(renderRow)}
          {displayDims.length > 0 && (
            <tr>
              <td colSpan={items.length + 1} className="px-4 pt-4 pb-1 text-xs text-gray-400">
                以下维度仅供参考
              </td>
            </tr>
          )}
          {displayDims.map(renderRow)}
        </tbody>
      </table>
    </div>
  );
}
