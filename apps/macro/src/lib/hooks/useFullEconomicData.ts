/**
 * 全量经济数据 Hook — 只负责 fetch，不做任何过滤
 * 由 page.tsx 顶层挂载一次，所有 Tab 共享同一份 fullData
 *
 * 关键点：
 * - 默认从 2000-01-01 拉全量（覆盖 ALL 时间范围，5-10MB JSON 现代浏览器完全可接受）
 * - localStorage 缓存（TTL 1h），setItem 失败静默（QuotaExceededError）
 * - cancelled flag 防止 unmount 后 setState（React 18 警告）
 */
'use client';

import { useState, useEffect } from 'react';
import type { EconomicDataResponse } from '../types/economic';
import { economicApi } from '../modules/economic/api';

export interface UseFullEconomicDataResult {
  fullData: EconomicDataResponse | null;
  isLoading: boolean;
  error: string | null;
  isCached: boolean;
}

const FULL_DATA_CACHE_KEY = 'economic_data_full_cache';
const CACHE_TTL_MS = 3600000; // 1h

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

export function useFullEconomicData(
  refreshKey: number = 0
): UseFullEconomicDataResult {
  const [fullData, setFullData] = useState<EconomicDataResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isCached, setIsCached] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const fetchFullData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // 手动刷新（refreshKey > 0）：跳过 cache
        if (refreshKey === 0) {
          const cached = localStorage.getItem(FULL_DATA_CACHE_KEY);
          if (cached) {
            const parsed = JSON.parse(cached);
            // 老格式 cache 视为失效（后端字段升级会导致结构变化）
            const isOldFormat = !parsed.data?.eu_treasuries;
            if (Date.now() - parsed.timestamp < CACHE_TTL_MS && !isOldFormat) {
              if (!cancelled) {
                setFullData(parsed.data);
                setIsCached(true);
                setIsLoading(false);
              }
              return;
            }
            if (isOldFormat) {
              localStorage.removeItem(FULL_DATA_CACHE_KEY);
            }
          }
        } else {
          // 手动刷新：清掉旧 cache
          localStorage.removeItem(FULL_DATA_CACHE_KEY);
        }

        // 从 2000-01-01 拉全量（覆盖 TIME_RANGE_MAP 的 ALL，与原 useEconomicData.ts 行为一致）
        const response = await economicApi.getData('2000-01-01', undefined);

        if (!cancelled) {
          setFullData(response);
          setIsCached(false);

          // 写入 localStorage（5-10MB JSON 可能超过 5MB 配额，静默失败）
          try {
            localStorage.setItem(
              FULL_DATA_CACHE_KEY,
              JSON.stringify({
                data: response,
                timestamp: Date.now(),
              })
            );
          } catch (e) {
            // QuotaExceededError 等 — 不阻断主流程，下次刷新会重拉
            console.warn('localStorage 写入失败（容量超限？）:', e);
          }
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : '获取数据失败';
          setError(message);
          console.error('获取经济数据失败:', err);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    fetchFullData();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // 兜底：loading 完成后 fullData 仍是 null（极少见，fetch 失败时返回 default）
  const safeFullData =
    fullData ?? (isLoading ? null : getDefaultEconomicData());

  return {
    fullData: safeFullData,
    isLoading,
    error,
    isCached,
  };
}
