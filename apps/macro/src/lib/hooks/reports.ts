/**
 * 分析报告看板数据 hooks
 * - useReports(source): 拉报告列表，source 变化重新请求
 * - useReportDetail(reportId): 懒加载——reportId 非空才请求单篇详情
 */
'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../api-client';
import type { ReportDetail, ReportListData, ReportMeta } from '../types/reports';

export interface UseReportsResult {
  reports: ReportMeta[];
  total: number;
  isLoading: boolean;
  error: string | null;
  reload: () => void;
}

export function useReports(source: string | null): UseReportsResult {
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await apiClient.get<ReportListData>('/api/macro/reports', {
          source: source ?? undefined,
        });
        if (!cancelled) {
          setReports(data.reports ?? []);
          setTotal(data.total ?? 0);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载报告列表失败');
          setReports([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [source, reloadKey]);

  return { reports, total, isLoading, error, reload };
}

export interface UseReportDetailResult {
  detail: ReportDetail | null;
  isLoading: boolean;
  error: string | null;
}

export function useReportDetail(reportId: string | null): UseReportDetailResult {
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) {
      setDetail(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      setError(null);
      setDetail(null);
      try {
        const data = await apiClient.get<ReportDetail>(
          `/api/macro/reports/${encodeURIComponent(reportId)}`
        );
        if (!cancelled) {
          setDetail(data);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载报告详情失败');
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  return { detail, isLoading, error };
}

/** 删除接口的管理 token 存 sessionStorage（仅当前标签页，不落代码/不进 bundle） */
export const DELETE_TOKEN_STORAGE_KEY = 'macro-report-upload-token';

export async function deleteReport(reportId: string, token: string): Promise<void> {
  await apiClient.delete(`/api/macro/reports/${encodeURIComponent(reportId)}`, undefined, {
    'X-Upload-Token': token,
  });
}
