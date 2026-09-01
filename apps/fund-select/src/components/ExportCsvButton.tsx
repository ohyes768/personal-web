/**
 * CSV 导出按钮（导出当前筛选结果）
 */
'use client';

import { ArrowDownTrayIcon } from '@heroicons/react/24/outline';
import { useState } from 'react';

import { fundApi } from '@/lib/api';
import type { FundFilters } from '@/lib/types';

interface ExportCsvButtonProps {
  filters: FundFilters;
}

export function ExportCsvButton({ filters }: ExportCsvButtonProps) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    setExporting(true);
    setError(null);
    try {
      await fundApi.exportCsv(filters);
    } catch (e) {
      setError(e instanceof Error ? e.message : '导出失败');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={handleExport}
        disabled={exporting}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-paper-deep text-ink-muted hover:bg-info-tint hover:text-info transition-colors disabled:opacity-50"
        aria-label="导出 CSV"
      >
        <ArrowDownTrayIcon className="w-4 h-4" />
        CSV
      </button>
      {error && (
        <span className="absolute right-0 top-full mt-1 text-[11px] text-down whitespace-nowrap">
          {error}
        </span>
      )}
    </div>
  );
}
