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
} from "./api";
import { mockEnabled, mockProjects, mockReportDetail, mockReports } from "./mock";

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

export function useProjects(): WithReload<ProjectSummary[]> {
  return useFetchWithMock<ProjectSummary[]>(
    useCallback(async () => {
      const d = await apiGet<{ projects: Record<string, unknown>[] }>("/projects");
      // 后端返回 last_activity + recent_summaries:[{title,summary_text,...}]；归一化成
      // 前端契约的 last_active_at + recent:string[]，字段缺失时安全兜底避免页面崩溃。
      return (d.projects ?? []).map((p) => {
        const s = p as {
          project?: string; last_activity?: string; last_active_at?: string;
          session_count?: number; commit_count?: number;
          recent_summaries?: { title?: string; summary_text?: string }[];
          recent?: string[];
        };
        const recent = Array.isArray(s.recent)
          ? s.recent
          : (s.recent_summaries ?? []).map((r) =>
              [r.title, r.summary_text].filter(Boolean).join(" — "),
            );
        return {
          project: s.project ?? "未知项目",
          last_active_at: s.last_active_at ?? s.last_activity ?? "",
          session_count: s.session_count ?? 0,
          commit_count: s.commit_count ?? 0,
          recent,
        };
      });
    }, []),
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
    useCallback(async () => {
      const d = await apiGet<Record<string, unknown>>(`/reports/${id}`);
      // 后端详情返回扁平结构（报告字段在顶层 + records）；归一化成 {report, records}，
      // 兼容旧版嵌套形状，避免 data.report 为 undefined 时页面崩溃。
      const nested = (d.report ?? null) as ReportDetail["report"] | null;
      if (nested) return { report: nested, records: (d.records as ReportDetail["records"]) ?? [] };
      const { records = [], ...report } = d;
      return { report: report as unknown as ReportDetail["report"], records: records as ReportDetail["records"] };
    }, [id]),
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

// 首页日历翻页用：日报日期索引（按 period_start 升序）+ 日期→id 映射
export function useDailyIndex(): {
  dates: string[];
  byDate: Record<string, string>;
  minDate: string;
  loading: boolean;
  error: string;
  reload: () => Promise<void>;
} {
  const { data, loading, error, reload } = useReports("daily");
  const dates = (data ?? []).map((r) => r.period_start).sort();
  const byDate: Record<string, string> = {};
  for (const r of data ?? []) byDate[r.period_start] = r.id;
  return { dates, byDate, minDate: dates[0] ?? "", loading, error, reload };
}
