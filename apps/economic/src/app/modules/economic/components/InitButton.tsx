'use client';

/**
 * 数据初始化按钮（首次部署用）
 * - 未初始化：蓝色高亮（饱和色 + 阴影/ring，比 RefreshButton 更醒目）
 * - 初始化中：转圈 + 高亮
 * - 已完成：置灰 + 显示"已初始化 YYYY-MM-DD HH:MM"，永久不可再点
 * - 通过 localStorage 持久化 initAt，刷新页面后保持置灰状态
 * - hasData prop（来自父组件 useEconomicData）：后端 CSV 已有数据时也置灰（兜底）
 *   检测到 hasData=true 且 localStorage 无值时，自动写入 localStorage 缓存
 */
import { useState, useEffect, useCallback } from 'react';
import type { UpdateResponse } from '@/lib/modules/economic/api';

interface InitButtonProps {
  onInit: () => Promise<UpdateResponse>;
  storageKey: string;
  label: string;
  hasData?: boolean;
}

export function InitButton({ onInit, storageKey, label, hasData = false }: InitButtonProps) {
  const [isInitializing, setIsInitializing] = useState(false);
  const [initAt, setInitAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 首次挂载读 localStorage
  useEffect(() => {
    try {
      const cached = localStorage.getItem(storageKey);
      if (cached) {
        setInitAt(cached);
      } else if (hasData) {
        // localStorage 没值但后端已有数据 → 写入缓存避免下次再判断
        const now = new Date().toISOString();
        try {
          localStorage.setItem(storageKey, now);
        } catch {
          /* ignore */
        }
        setInitAt(now);
      }
    } catch {
      /* ignore */
    }
  }, [storageKey, hasData]);

  // 综合判断：localStorage 有值 || 后端已有数据 → 视为已初始化
  const isInitialized = !!initAt || hasData;

  const handleClick = useCallback(async () => {
    if (isInitializing || isInitialized) return;
    setIsInitializing(true);
    setError(null);
    try {
      const res = await onInit();
      if (res.success) {
        const now = new Date().toISOString();
        try {
          localStorage.setItem(storageKey, now);
        } catch {
          /* ignore */
        }
        setInitAt(now);
      } else {
        setError(res.message || res.error_code || '初始化失败');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '初始化失败');
    } finally {
      setIsInitializing(false);
    }
  }, [isInitializing, isInitialized, onInit, storageKey]);

  // 已完成：置灰 + 显示初始化时间
  if (isInitialized) {
    const displayTime = initAt
      ? new Date(initAt).toLocaleString('zh-CN', { hour12: false })
      : '（数据已存在）';
    return (
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled
          className="px-4 py-2 rounded-lg bg-gray-800 text-gray-500 cursor-not-allowed flex items-center gap-2"
          title={initAt ? `已初始化：${displayTime}` : '后端已有数据，无需初始化'}
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          <span>已初始化</span>
        </button>
        <span className="text-xs text-gray-500" title={`如需重新初始化，请在浏览器控制台执行：localStorage.removeItem('${storageKey}')`}>
          {displayTime}
        </span>
      </div>
    );
  }

  // 初始化中：转圈 + 高亮
  if (isInitializing) {
    return (
      <button
        type="button"
        disabled
        className="px-4 py-2 rounded-lg font-medium bg-amber-500 text-white shadow-lg shadow-amber-500/50 ring-2 ring-amber-400 ring-offset-2 ring-offset-black flex items-center gap-2 cursor-not-allowed"
      >
        <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.3" />
          <path
            d="M4 12a8 8 0 018-8"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
        初始化中...
      </button>
    );
  }

  // 未初始化：高亮（饱和蓝色 + 阴影 + ring）
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={handleClick}
        className="px-4 py-2 rounded-lg font-semibold bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/50 ring-2 ring-blue-400 ring-offset-2 ring-offset-black hover:from-blue-400 hover:to-indigo-500 hover:shadow-blue-400/60 transition-all flex items-center gap-2"
      >
        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5-5 5 5M12 5v12" />
        </svg>
        {label}
      </button>
      {error && <span className="text-sm text-red-400">{error}</span>}
    </div>
  );
}