/**
 * useRealtimePrices — 挡位监控专用现价 Hook
 *
 * 与 useTechnicalData（走 /api/dividend/m120）解耦：直接读 /api/dividend/prices，
 * M120 数据缺失时仍能拿到现价/PE/PB/yield_ttm，保证挡位监控 bar 不空窗。
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
import { dividendApi } from '@/lib/api';
import type { PriceItem } from '@/lib/types';

export function useRealtimePrices(codes: string[]) {
  const [priceMap, setPriceMap] = useState<Map<string, PriceItem>>(new Map());
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // 缓存 codes 引用，避免每次渲染触发 fetch（与 useTechnicalData 一致）
  const memoCodes = useMemo(() => codes, [JSON.stringify(codes)]);

  useEffect(() => {
    if (memoCodes.length === 0) {
      setPriceMap(new Map());
      setLastUpdated(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    dividendApi
      .getPrices(memoCodes)
      .then(res => {
        if (cancelled) return;
        const m = new Map<string, PriceItem>();
        for (const it of res.items ?? []) m.set(it.code, it);
        setPriceMap(m);
        // 现价更新时间取后端返回的实时价格文件 mtime（res.last_updated），
        // 而非访问时间，与挡位监控 bar 展示的现价同源。
        setLastUpdated(res.last_updated ?? null);
      })
      .catch(err => {
        console.error('[useRealtimePrices] fetch failed:', err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [memoCodes]);

  return { priceMap, lastUpdated, loading };
}
