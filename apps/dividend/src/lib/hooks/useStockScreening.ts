/**
 * useStockScreening — 只读加载单股的筛选复核结果 + 全池状态映射
 *
 * 判定规则与选股关注页同源（后端 screening_service.build_checks），前端只负责展示。
 * 条件取选股关注页保存在 localStorage 的那一份，没有保存时用默认条件。
 * 换公司时清空上一家的结果，避免把甲公司的判定显示在乙公司的报告上。
 *
 * 状态映射（全池每股 code → status）只拉一次，供下拉列表标注 ✓/✗/？；
 * 判定失败不阻断报告正文。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { dividendApi } from '@/lib/api';
import {
  readStoredScreeningConditions,
  type ScreeningStatus,
  type StockScreeningResponse,
} from '@/lib/screening';

export interface StockScreeningState {
  /** 当前公司的复核结果；换公司途中为 null */
  data: StockScreeningResponse | null;
  /** 首次加载中 */
  loading: boolean;
  /** 最近一次失败原因 */
  error: string | null;
  /** 全池每股筛选状态；加载失败为 null（下拉不显示标记） */
  statusMap: Record<string, ScreeningStatus> | null;
  /** 重新拉取（换篇后自动触发，手动刷新用） */
  reload: () => void;
}

export function useStockScreening(code: string | null): StockScreeningState {
  const [data, setData] = useState<StockScreeningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMap, setStatusMap] = useState<Record<string, ScreeningStatus> | null>(null);
  const requestSeq = useRef(0);
  const mounted = useRef(true);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    const seq = ++requestSeq.current;
    if (!code) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    // 条件在浏览器里读：SSR 阶段没有 localStorage，effect 只在客户端跑
    const conditions = readStoredScreeningConditions();
    setData(null);
    setError(null);
    setLoading(true);
    dividendApi.getStockScreening(code, conditions)
      .then(response => {
        if (!mounted.current || seq !== requestSeq.current) return;
        setData(response);
      })
      .catch(err => {
        if (!mounted.current || seq !== requestSeq.current) return;
        setError(err instanceof Error ? err.message : '筛选复核加载失败');
      })
      .finally(() => {
        if (mounted.current && seq === requestSeq.current) setLoading(false);
      });
  }, [code, reloadToken]);

  // 全池状态映射：只拉一次（条件来自 localStorage，本会话内不变；刷新按钮可重拉）
  useEffect(() => {
    if (reloadToken === 0) return;
    const conditions = readStoredScreeningConditions();
    dividendApi.getScreeningStatuses(conditions)
      .then(response => {
        if (!mounted.current) return;
        const map: Record<string, ScreeningStatus> = {};
        for (const item of response.items) map[item.code] = item.status;
        setStatusMap(map);
      })
      .catch(() => { if (mounted.current) setStatusMap(null); });
  }, [reloadToken]);

  // 首次进入页面拉一次状态映射（独立于单股判定，失败静默）
  useEffect(() => {
    const conditions = readStoredScreeningConditions();
    let cancelled = false;
    dividendApi.getScreeningStatuses(conditions)
      .then(response => {
        if (cancelled) return;
        const map: Record<string, ScreeningStatus> = {};
        for (const item of response.items) map[item.code] = item.status;
        setStatusMap(map);
      })
      .catch(() => { if (!cancelled) setStatusMap(null); });
    return () => { cancelled = true; };
  }, []);

  const reload = useCallback(() => setReloadToken(token => token + 1), []);

  return { data, loading, error, statusMap, reload };
}
