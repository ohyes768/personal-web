/**
 * 报告列表：来源筛选（全部/A股宏观展望/利率债展望）+ 报告条目
 * 条目显示分析日期 + 标题按「｜」拆出的方向词；选中高亮
 */
'use client';

import type { ReportMeta } from '@/lib/types/reports';
import { REPORT_SOURCE_LABELS } from '@/lib/types/reports';

interface ReportListProps {
  reports: ReportMeta[];
  total: number;
  isLoading: boolean;
  error: string | null;
  activeSource: string;
  selectedId: string | null;
  onSourceChange: (source: string) => void;
  onSelect: (reportId: string) => void;
  onReload: () => void;
}

/** 标题按「｜」拆分：首段=日期+来源短语，其余段=方向/细分词 */
function splitTitle(title: string): { head: string; tags: string[] } {
  const segments = title.split('｜').map((s) => s.trim()).filter(Boolean);
  if (segments.length <= 1) {
    return { head: title, tags: [] };
  }
  return { head: segments[0], tags: segments.slice(1) };
}

export function ReportList({
  reports,
  total,
  isLoading,
  error,
  activeSource,
  selectedId,
  onSourceChange,
  onSelect,
  onReload,
}: ReportListProps) {
  const filters = [
    { value: '', label: '全部' },
    ...Object.entries(REPORT_SOURCE_LABELS).map(([value, label]) => ({ value, label })),
  ];

  return (
    <div className="flex flex-col h-full">
      {/* 来源筛选 */}
      <div className="flex flex-wrap gap-2 mb-4">
        {filters.map((f) => (
          <button
            key={f.value || 'all'}
            type="button"
            onClick={() => onSourceChange(f.value)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
              activeSource === f.value
                ? 'bg-blue-600 border-blue-600 text-white'
                : 'bg-gray-900 border-gray-700 text-gray-300 hover:bg-gray-800'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="text-center text-gray-400 py-12">加载中...</div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-400 mb-3 text-sm">{error}</p>
          <button
            type="button"
            onClick={onReload}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-700 text-gray-300 hover:bg-gray-800 transition-colors"
          >
            重试
          </button>
        </div>
      ) : reports.length === 0 ? (
        <div className="text-center text-gray-400 py-12">暂无报告</div>
      ) : (
        <ul className="space-y-2">
          {reports.map((report) => {
            const { head, tags } = splitTitle(report.title);
            const isSelected = report.report_id === selectedId;
            return (
              <li key={report.report_id}>
                <button
                  type="button"
                  onClick={() => onSelect(report.report_id)}
                  className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
                    isSelected
                      ? 'bg-gray-800 border-blue-500'
                      : 'bg-gray-900 border-gray-800 hover:bg-gray-800'
                  }`}
                >
                  <div className="text-xs text-gray-400 mb-1">
                    {report.analyzed_at.slice(0, 10)}
                    <span className="ml-2 text-gray-600">
                      {REPORT_SOURCE_LABELS[report.source] ?? report.source}
                    </span>
                  </div>
                  <div className="text-sm font-medium text-white truncate">{head}</div>
                  {tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-300"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {!isLoading && !error && reports.length > 0 && (
        <p className="text-xs text-gray-500 mt-3">共 {total} 篇</p>
      )}
    </div>
  );
}
