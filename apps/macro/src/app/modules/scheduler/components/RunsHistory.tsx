'use client';

/**
 * 运行历史列表 — 最近 20 条运行记录，每条可再展开数据源子明细（ItemTable）
 */
import { useState } from 'react';
import type { SchedulerJobRun } from '@/lib/modules/scheduler/types';
import { ItemTable } from './ItemTable';
import { STATUS_META, formatTs, durationOf } from './runUtils';

interface RunsHistoryProps {
  runs?: SchedulerJobRun[];
  loading: boolean;
  onRefresh: () => void;
}

export function RunsHistory({ runs, loading, onRefresh }: RunsHistoryProps) {
  // 当前展开子明细的运行记录 key（start + 序号）
  const [expandedRunKey, setExpandedRunKey] = useState<string | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-400">最近 20 条历史（最新在前，点条目展开数据源明细）</span>
        <button
          onClick={onRefresh}
          className="text-xs text-blue-400 hover:underline"
          disabled={loading}
        >
          {loading ? '加载中…' : '刷新'}
        </button>
      </div>
      {loading && !runs ? (
        <div className="text-center text-gray-500 py-4 text-xs">加载中...</div>
      ) : !runs || runs.length === 0 ? (
        <div className="text-center text-gray-500 py-4 text-xs">暂无执行历史</div>
      ) : (
        <div className="space-y-1 max-h-96 overflow-y-auto">
          {runs.map((r, i) => {
            const runKey = `${r.start}-${i}`;
            const expanded = expandedRunKey === runKey;
            const hasItems = Array.isArray(r.items) && r.items.length > 0;
            return (
              <div key={runKey} className="border-b border-gray-800 last:border-b-0">
                <div
                  className="flex items-start gap-2 text-xs py-1.5 flex-wrap"
                  // 有子明细的条目可点击展开/收起
                  onClick={() => hasItems && setExpandedRunKey(expanded ? null : runKey)}
                  style={hasItems ? { cursor: 'pointer' } : undefined}
                >
                  <span className={`px-1.5 py-0.5 rounded border ${STATUS_META[r.status]?.cls ?? ''}`}>
                    {STATUS_META[r.status]?.label ?? r.status}
                  </span>
                  <span className="text-gray-400 whitespace-nowrap">{formatTs(r.start)}</span>
                  {r.end && <span className="text-gray-500 whitespace-nowrap">{durationOf(r)}</span>}
                  {r.count != null && <span className="text-gray-300">{r.count} 成功</span>}
                  {r.reason && <span className="text-gray-500">({r.reason})</span>}
                  {r.error && (
                    <span
                      className="text-red-300 flex-1 min-w-0 truncate"
                      title={r.error}
                      onClick={(e) => {
                        // 阻止冒泡：点错误只复制，不触发展开
                        e.stopPropagation();
                        navigator.clipboard?.writeText(r.error || '');
                      }}
                      style={{ cursor: 'pointer' }}
                    >
                      {r.error}
                    </span>
                  )}
                  {hasItems && (
                    <span className="text-gray-500">{expanded ? '▲' : '▼'}</span>
                  )}
                </div>
                {expanded && hasItems && (
                  <div className="pl-6 pb-2">
                    <ItemTable items={r.items!} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
