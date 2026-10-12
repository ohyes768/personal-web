'use client';

import { useEffect, useState } from 'react';
import { RENTAL_DATA_CHANGED } from './rental-sources';
import {
  buildRentalDetailPath,
  fetchRentalData,
  type RentalDetailData,
  type RentalDetailQuery,
} from './rental-types';

export interface RentalDataState {
  data?: RentalDetailData;
  error?: string;
}

export interface UseRentalDataResult extends RentalDataState {
  /** 请求 key 与当前参数不一致时视为加载中（含切小区、切筛选） */
  loading: boolean;
}

/**
 * 小区租金详情数据 hook。
 * - 只在挂载（rental 标签激活）后请求；
 * - 小区 id 或查询参数变化时通过 AbortController 取消旧请求；
 * - 组件卸载时 abort 清理；reloadKey 变化用于失败后手动重试。
 */
export function useRentalData(communityId: string, query: RentalDetailQuery, reloadKey = 0): UseRentalDataResult {
  const { areaBand, bedrooms, page, view } = query;
  const [state, setState] = useState<(RentalDataState & { key: string }) | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const reload = () => setRevision(v => v + 1);
    window.addEventListener(RENTAL_DATA_CHANGED, reload);
    return () => window.removeEventListener(RENTAL_DATA_CHANGED, reload);
  }, []);
  const key = `${communityId}|${areaBand}|${bedrooms}|${page}|${view}|${reloadKey}|${revision}`;

  useEffect(() => {
    const controller = new AbortController();
    fetchRentalData<RentalDetailData>(buildRentalDetailPath(communityId, { areaBand, bedrooms, page, view }), controller.signal)
      .then(data => {
        if (!controller.signal.aborted) setState({ key, data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ key, error: '租金数据暂时不可用' });
      });
    return () => controller.abort();
  }, [communityId, areaBand, bedrooms, page, view, reloadKey, key]);

  const current = state && state.key === key ? state : null;
  return {
    data: current?.data,
    error: current?.error,
    loading: !current,
  };
}
