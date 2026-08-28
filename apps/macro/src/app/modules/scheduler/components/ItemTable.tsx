'use client';

/**
 * 数据源子明细表 — 组任务一次运行里每个 update 端点的结果
 * 列：路径 / 状态 / 条数 / 耗时 / 错误（错误点击可复制）
 */
import type { SchedulerRunItem } from '@/lib/modules/scheduler/types';

interface ItemTableProps {
  items: SchedulerRunItem[];
}

const ITEM_STATUS_CLS: Record<SchedulerRunItem['status'], string> = {
  success: 'text-green-300',
  failed: 'text-red-300',
};

export function ItemTable({ items }: ItemTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b border-gray-800">
            <th className="text-left font-normal py-1.5 pr-4">数据源</th>
            <th className="text-left font-normal py-1.5 pr-4">状态</th>
            <th className="text-right font-normal py-1.5 pr-4">条数</th>
            <th className="text-right font-normal py-1.5 pr-4">耗时</th>
            <th className="text-left font-normal py-1.5">错误</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr key={`${item.path}-${i}`} className="border-b border-gray-800/60 last:border-b-0">
              <td className="py-1.5 pr-4 whitespace-nowrap">
                <code className="bg-gray-800 px-1.5 py-0.5 rounded text-gray-300">{item.path}</code>
              </td>
              <td className={`py-1.5 pr-4 ${ITEM_STATUS_CLS[item.status] ?? 'text-gray-400'}`}>
                {item.status === 'success' ? '成功' : '失败'}
              </td>
              <td className="py-1.5 pr-4 text-right text-gray-400">
                {item.count ?? '-'}
              </td>
              <td className="py-1.5 pr-4 text-right text-gray-500 whitespace-nowrap">
                {item.ms != null ? `${item.ms}ms` : '-'}
              </td>
              <td className="py-1.5 text-gray-400 max-w-0">
                {item.error ? (
                  <span
                    className="text-red-300 truncate block"
                    style={{ cursor: 'pointer' }}
                    title={item.error}
                    onClick={() => navigator.clipboard?.writeText(item.error || '')}
                  >
                    {item.error}
                  </span>
                ) : (
                  '-'
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
