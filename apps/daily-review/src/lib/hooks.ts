"use client";

// 取数 hooks：统一 loading / error / data 三态；
// NEXT_PUBLIC_DAILY_REVIEW_MOCK=1 时 fetch 失败回落 mock 数据（仅开发兜底）。
import { useCallback, useEffect, useState } from "react";
import {
  apiGet,
  apiSend,
  type ProjectSummary,
  type ReportDetail,
  type ReportMeta,
  type ReportType,
  type TodayData,
} from "./api";
import { mockEnabled, mockProjects, mockReportDetail, mockReports, mockToday } from "./mock";

type WithReload<T> = {
  data: T | null;
  loading: boolean;
  error: string;
  reload: () => Promise<void>;
};

function useFetchWithMock<T>(fetcher: () => Promise<T>, mock: () => T): WithReload<T> {
  const [state, setState] = useState<{ data: T | null; loading: boolean; error: string }>({
    data: null,
    loading: true,
    error: "",
  });

  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fetcher();
      setState({ data, loading: false, error: "" });
    } catch (e) {
      if (mockEnabled()) {
        setState({ data: mock(), loading: false, error: "" });
        return;
      }
      setState((s) => ({ ...s, loading: false, error: e instanceof Error ? e.message : String(e) }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);

  return { ...state, reload };
}

export function useToday(date: string): WithReload<TodayData> {
  return useFetchWithMock<TodayData>(
    useCallback(() => apiGet<TodayData>(`/today?date=${date}`), [date]),
    () => mockToday(date),
  );
}

export function useProjects(): WithReload<ProjectSummary[]> {
  return useFetchWithMock<ProjectSummary[]>(
    useCallback(() => apiGet<{ projects: ProjectSummary[] }>("/projects").then((d) => d.projects), []),
    () => mockProjects,
  );
}

export function useReports(type: ReportType): WithReload<ReportMeta[]> {
  return useFetchWithMock<ReportMeta[]>(
    useCallback(
      () => apiGet<{ reports: ReportMeta[] }>(`/reports?type=${type}`).then((d) => d.reports),
      [type],
    ),
    () => mockReports.filter((r) => r.report_type === type),
  );
}

export function useReport(id: string): WithReload<ReportDetail> {
  return useFetchWithMock<ReportDetail>(
    useCallback(() => apiGet<ReportDetail>(`/reports/${id}`), [id]),
    () => mockReportDetail(id),
  );
}

export async function generateReport(
  report_type: ReportType,
  period_start?: string,
  period_end?: string,
): Promise<{ id: string }> {
  return apiSend<{ id: string }>("POST", "/reports/generate", {
    report_type,
    period_start,
    period_end,
  });
}
