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
import { mockEnabled, mockProjects, mockReportDetail, mockReports, mockUsage } from "./mock";
import { getUsage, type UsageData } from "./api";

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
  }, [fetcher]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { ...state, reload };
}

export function useProjects(days: number): WithReload<ProjectSummary[]> {
  return useFetchWithMock<ProjectSummary[]>(
    useCallback(
      () => apiGet<{ projects: ProjectSummary[] }>(`/projects?days=${days}`).then((d) => d.projects),
      [days],
    ),
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
  const inner = useFetchWithMock<ReportDetail>(
    useCallback(async () => {
      // id 为空/占位时跳过请求（首页日历翻页在索引未加载或无报日期会传占位值），
      // 页面在该情形下不会渲染 data，返回空壳即可
      if (!id || id === "__none__") return { report: null, records: [] } as unknown as ReportDetail;
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
  return inner;
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

// 单日 Token 用量：辅助信息，失败静默（旧后端 404 时不渲染用量行，不阻塞主内容）
export function useUsage(date: string): { data: UsageData | null } {
  const [data, setData] = useState<UsageData | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    getUsage({ date })
      .then((d) => alive && setData(d))
      .catch(() => {
        if (!mockEnabled()) return;
        alive && setData(mockUsage(date));
      });
    return () => {
      alive = false;
    };
  }, [date]);
  return { data };
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
