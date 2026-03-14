/**
 * 刷新按钮组件
 * 用于刷新单只股票的实时股价和偏离度
 */
'use client';

import { useState, useEffect } from 'react';
import type { RefreshState } from '@/lib/modules/dividend/types';

export interface RefreshButtonProps {
  code: string;
  m120: number;
  onRefresh: (code: string, m120: number) => Promise<{ close: number; deviation: number } | null>;
  refreshState: RefreshState;
}

export function RefreshButton({ code, m120, onRefresh, refreshState }: RefreshButtonProps) {
  const [localLoading, setLocalLoading] = useState(false);
  const [showError, setShowError] = useState(false);

  // 处理刷新点击
  const handleClick = async () => {
    setLocalLoading(true);
    setShowError(false);

    try {
      await onRefresh(code, m120);
    } catch (err) {
      console.error('刷新失败:', err);
      setShowError(true);
      // 3秒后隐藏错误提示
      setTimeout(() => setShowError(false), 3000);
    } finally {
      setLocalLoading(false);
    }
  };

  // 同步外部状态
  useEffect(() => {
    if (!refreshState.loading) {
      setLocalLoading(false);
    }
  }, [refreshState.loading]);

  // 显示错误提示
  useEffect(() => {
    if (refreshState.error && !localLoading) {
      setShowError(true);
      const timer = setTimeout(() => setShowError(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [refreshState.error, localLoading]);

  const isLoading = localLoading || refreshState.loading;

  return (
    <div className="relative">
      <button
        onClick={handleClick}
        disabled={isLoading}
        className={`w-5 h-5 flex items-center justify-center rounded transition-colors ${
          isLoading
            ? 'text-gray-500 cursor-not-allowed'
            : showError
            ? 'text-red-400 hover:text-red-300'
            : 'text-gray-400 hover:text-white hover:bg-gray-700'
        }`}
        title="刷新实时股价"
      >
        {isLoading ? (
          <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        ) : (
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        )}
      </button>

      {showError && refreshState.error && (
        <div className="absolute bottom-full right-0 mb-1 px-2 py-0.5 bg-red-900 text-white text-xs rounded whitespace-nowrap z-10">
          {refreshState.error}
        </div>
      )}
    </div>
  );
}