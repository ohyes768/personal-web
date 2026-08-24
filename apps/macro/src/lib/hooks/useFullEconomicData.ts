/**
 * 全量经济数据 Hook — 只负责 fetch，不做任何过滤
 * 由 page.tsx 顶层挂载一次，所有 Tab 共享同一份 fullData
 *
 * 分层加载策略（替代原"首屏拉 26 年全量"）：
 * - 阶段 1（首屏）：请求近 1 年数据，渲染立即开始
 * - 阶段 2（后台）：requestIdleCallback（兜底 setTimeout 2s）请求 2000 年至今全量，
 *                 替换 fullData，供 ALL 档使用
 * - 手动刷新（refreshKey > 0）：直接拉全量 + cache:'reload' 拿最新数据
 *
 * localStorage 缓存已移除：
 * - HTTP 响应头 Cache-Control: public, max-age=300（后端）让浏览器 disk cache 覆盖 TTL 内访问
 * - 几 MB JSON 同步 parse 阻塞主线程 + 写入常超 5MB 配额静默失败
 * - isCached 字段保留以兼容现有 Tab 组件 props，移除 localStorage 后恒 false
 *   （"（缓存）" UI 标签的归宿见 .trellis/tasks/08-24-macro-page-perf/prd.md P2 死代码项）
 *
 * 关键点：
 * - 首屏用 native fetch 直连 /api/macro/data，不走 economicApi 抽象，
 *   以便手动刷新时透传 {cache:'reload'} 绕过 5min 浏览器缓存
 * - cancelled flag 防止 unmount 后 setState（React 18 警告）
 */
'use client';

import { useState, useEffect } from 'react';
import type { EconomicDataResponse } from '../types/economic';

export interface UseFullEconomicDataResult {
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
  /** 当前 fullData 是否覆盖到 ALL 时间范围（true 后 ALL 档可正常渲染） */
  isFullRange: boolean;
}

// 首屏阶段 1：拉近 1 年（覆盖默认 3M/6M/1Y 时间范围；与原行为一致的 1Y 起点）
const STAGE1_START_DATE = '2025-08-24';
// 阶段 2 + 手动刷新：全量起始（与历史 settings 一致）
const FULL_START_DATE = '2000-01-01';

// 默认的经济数据结构（保证 filter 时不报 undefined.length）
function getDefaultEconomicData(): EconomicDataResponse {
  return {
    dates: [],
    us_treasuries: { '3m': [], '2y': [], '10y': [] },
    eu_treasuries: { '3m': [], '2y': [], '10y': [] },
    jp_treasuries: { '3m': [], '2y': [], '10y': [] },
    exchange_rates: {
      dollar_index: [],
      usd_cny: [],
      usd_jpy: [],
      usd_eur: [],
    },
    vix: [],
    commodities: {
      gold: [],
      silver: [],
      oil: [],
      copper: [],
    },
    indices: {
      HKHSI: [],
      SH000001: [],
      SPX: [],
      IXIC: [],
      DJI: [],
    },
    tga: [],
    hibor: [],
  };
}

/**
 * 直接 fetch /api/macro/data，不走 economicApi 抽象以便透传 cache 选项。
 * 后端响应是 {success, data} 包裹，剥离后返回 data。
 */
async function fetchMacroData(
  startDate: string,
  options?: { cache?: RequestCache }
): Promise<EconomicDataResponse> {
  const url = `/api/macro/data?start_date=${startDate}`;
  const res = await fetch(url, options);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  const body = (await res.json()) as { success: boolean; data?: EconomicDataResponse; error?: string };
  if (!body.success) {
    throw new Error(body.error || 'API request failed');
  }
  return body.data!;
}

export function useFullEconomicData(
  refreshKey: number = 0
): UseFullEconomicDataResult {
  const [fullData, setFullData] = useState<EconomicDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCached] = useState(false); // 恒 false（保留字段以兼容 Tab 组件 props）
  const [isFullRange, setIsFullRange] = useState(false);

  useEffect(() => {
    let cancelled = false;

    // 手动刷新（refreshKey > 0）：直接拉全量 + cache:'reload' 拿最新数据，跳过分层
    if (refreshKey > 0) {
      const refreshFull = async () => {
        setIsLoading(true);
        setError(null);
        try {
          const data = await fetchMacroData(FULL_START_DATE, { cache: 'reload' });
          if (!cancelled) {
            setFullData(data);
            setIsFullRange(true);
          }
        } catch (err) {
          if (!cancelled) {
            const message = err instanceof Error ? err.message : '获取数据失败';
            setError(message);
            console.error('刷新经济数据失败:', err);
          }
        } finally {
          if (!cancelled) setIsLoading(false);
        }
      };
      refreshFull();
      return () => { cancelled = true; };
    }

    // 阶段 1：拉近 1 年数据（默认 HTTP 缓存策略，TTL 内浏览器 disk cache 命中）
    const stage1 = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchMacroData(STAGE1_START_DATE);
        if (!cancelled) {
          setFullData(data);
          setIsFullRange(false);
          setIsLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : '获取数据失败';
          setError(message);
          console.error('获取经济数据失败:', err);
          setIsLoading(false);
        }
      }
    };
    stage1();

    // 阶段 2：requestIdleCallback 拉全量（兜底 setTimeout 2s）
    // 为什么用 requestIdleCallback：首屏渲染完后 CPU 空闲时再做重活，不阻塞主线程；
    // 但如果浏览器不支持或长时间不空闲（用户一直滚动），2s 后强制拉取保证 ALL 档可用
    const scheduleFull = (cb: () => void) => {
      type IdleApi = {
        requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      };
      const w = window as Window & IdleApi;
      if (typeof w.requestIdleCallback === 'function') {
        w.requestIdleCallback(cb, { timeout: 2000 });
      } else {
        setTimeout(cb, 2000);
      }
    };

    let stage2Done = false;
    const runStage2 = async () => {
      if (stage2Done) return;
      stage2Done = true;
      try {
        const data = await fetchMacroData(FULL_START_DATE);
        if (!cancelled) {
          setFullData(data);
          setIsFullRange(true);
        }
      } catch (err) {
        // 阶段 2 失败不影响阶段 1 数据；只在 ALL 档时才显式报错
        console.warn('全量数据后台拉取失败:', err);
      }
    };
    scheduleFull(runStage2);

    return () => { cancelled = true; };
  }, [refreshKey]);

  // 兜底：loading 完成后 fullData 仍是 null（极少见，fetch 失败时返回 default）
  const safeFullData =
    fullData ?? (isLoading ? null : getDefaultEconomicData());

  return {
    fullData: safeFullData,
    isLoading,
    error,
    isCached,
    isFullRange,
  };
}