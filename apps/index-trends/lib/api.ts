import type {
  ChartData,
  Valuation,
  CurrentModelKind,
  CurrentStatus,
  HistoryOverview,
  IndicesOverview,
  RefreshResult,
  ValuationHistory,
  ValuationMetric,
} from "./types";
import { DEFAULT_INDEX_CODE } from "./indexes";

const BASE = "/api/index-trends";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${resp.status}`;
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export const api = {
  indices: () => fetchJSON<IndicesOverview>("/indices"),
  history: (code: string = DEFAULT_INDEX_CODE) =>
    fetchJSON<HistoryOverview>(`/indices/${code}/history`),
  chart: (code: string, modelId: string, scope: "history" | "current") =>
    fetchJSON<ChartData>(
      `/indices/${code}/chart?model=${encodeURIComponent(modelId)}&scope=${scope}`,
    ),
  status: (code: string, model: CurrentModelKind) =>
    fetchJSON<CurrentStatus>(`/indices/${code}/status?model=${model}`),
  valuation: (code: string) => fetchJSON<Valuation>(`/indices/${code}/valuation`),
  valuationHistory: (code: string, metric: ValuationMetric) =>
    fetchJSON<ValuationHistory>(`/indices/${code}/valuation/history?metric=${metric}`),
  refresh: (code: string = DEFAULT_INDEX_CODE) =>
    fetchJSON<RefreshResult>(`/refresh?index_code=${code}`, { method: "POST" }),
};
