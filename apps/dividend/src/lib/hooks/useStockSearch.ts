/**
 * useStockSearch — 「全部」页股票搜索 Hook
 *
 * - 300ms 防抖：连续输入只发一次请求
 * - 响应序号：慢的旧响应不会覆盖新关键词的结果
 * - 关键词为空 / 页面未启用 / 收藏范围为空 → 清空结果且不发请求
 *
 * 搜索范围由后端决定：命中完整收集池（不受股息率阈值限制），
 * `codes` 传入时与之取交集（「只看收藏」）。
 */
'use client';

import { useEffect, useRef, useState } from 'react';
import { dividendApi } from '@/lib/api';
import { buildStockSearchParams, normalizeSearchKeyword } from '@/lib/stock-search';
import type { DividendStock } from '@/lib/types';

/** 输入防抖时长（毫秒） */
const SEARCH_DEBOUNCE_MS = 300;

export interface UseStockSearchResult {
  /** 命中股票（后端已按相关度排序） */
  results: DividendStock[];
  /** 请求进行中（含防抖等待） */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
}

/**
 * @param enabled 页面是否启用搜索（非「全部」Tab 时为 false）
 * @param keyword 原始输入（内部归一）
 * @param codes 逗号分隔的代码范围；undefined = 不限；'' = 限定为空集合
 */
export function useStockSearch(
  enabled: boolean,
  keyword: string,
  codes?: string,
): UseStockSearchResult {
  const [results, setResults] = useState<DividendStock[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeqRef = useRef(0);

  const normalized = normalizeSearchKeyword(keyword);
  const scopeCodes = codes?.trim();

  useEffect(() => {
    // 未启用 / 无关键词 / 收藏范围为空：清空结果，不发请求
    // （scopeCodes === '' 表示「只看收藏」但收藏为空，不能退化成全池搜索）
    if (!enabled || !normalized || scopeCodes === '') {
      requestSeqRef.current += 1; // 作废在途请求
      setResults([]);
      setLoading(false);
      setError(null);
      return;
    }

    const seq = ++requestSeqRef.current;
    setLoading(true);
    setError(null);

    const timer = setTimeout(async () => {
      try {
        const response = await dividendApi.getStocks(
          buildStockSearchParams(normalized, scopeCodes),
        );
        if (seq !== requestSeqRef.current) return; // 旧响应，丢弃
        setResults(response.items);
      } catch (err) {
        if (seq !== requestSeqRef.current) return;
        setResults([]);
        setError(err instanceof Error ? err.message : '股票搜索失败');
      } finally {
        if (seq === requestSeqRef.current) setLoading(false);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [enabled, normalized, scopeCodes]);

  return { results, loading, error };
}
