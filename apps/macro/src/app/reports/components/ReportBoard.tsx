/**
 * 报告看板容器：来源筛选状态 + 选中报告状态 + 两栏布局
 * lg 及以上：左列表（固定宽 320px，自身滚动）右详情两栏常驻
 * lg 以下：单栏，未选中显示列表、选中显示详情（详情内有返回按钮）
 */
'use client';

import { useCallback, useState } from 'react';
import { useReports, useReportDetail } from '@/lib/hooks/reports';
import { ReportList } from './ReportList';
import { ReportViewer } from './ReportViewer';

export function ReportBoard() {
  /** 来源筛选：'' = 全部 */
  const [activeSource, setActiveSource] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { reports, total, isLoading, error, reload } = useReports(activeSource || null);
  const {
    detail,
    isLoading: detailLoading,
    error: detailError,
  } = useReportDetail(selectedId);

  const handleSourceChange = useCallback((source: string) => {
    setActiveSource(source);
    setSelectedId(null); // 切筛选后原选中项可能不在新列表内，回列表
  }, []);

  const handleSelect = useCallback((reportId: string) => {
    setSelectedId(reportId);
  }, []);

  const handleBack = useCallback(() => {
    setSelectedId(null);
  }, []);

  return (
    <div className="lg:flex lg:gap-6 lg:items-start">
      {/* 列表栏：移动端未选中时显示；lg 常驻固定宽 */}
      <div
        className={`${selectedId ? 'hidden' : 'block'} lg:block lg:w-80 lg:shrink-0 lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto`}
      >
        <ReportList
          reports={reports}
          total={total}
          isLoading={isLoading}
          error={error}
          activeSource={activeSource}
          selectedId={selectedId}
          onSourceChange={handleSourceChange}
          onSelect={handleSelect}
          onReload={reload}
        />
      </div>

      {/* 详情栏：移动端选中时显示；lg 常驻占满剩余宽度 */}
      <div
        className={`${selectedId ? 'block' : 'hidden'} lg:block flex-1 min-w-0 lg:max-h-[calc(100vh-14rem)] lg:overflow-y-auto`}
      >
        <ReportViewer
          detail={detail}
          isLoading={detailLoading}
          error={detailError}
          onBack={handleBack}
        />
      </div>
    </div>
  );
}
