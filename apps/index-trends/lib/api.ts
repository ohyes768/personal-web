import type {
  ChartData,
  CurrentStatus,
  HistoryOverview,
  IndicesOverview,
  RefreshResult,
} from "./types";

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
  history: () => fetchJSON<HistoryOverview>("/indices/000300/history"),
  chart: (modelId: string, scope: "history" | "current") =>
    fetchJSON<ChartData>(
      `/indices/000300/chart?model=${encodeURIComponent(modelId)}&scope=${scope}`,
    ),
  status: (model: "trailing_120m" | "since_inception") =>
    fetchJSON<CurrentStatus>(`/indices/000300/status?model=${model}`),
  refresh: () => fetchJSON<RefreshResult>("/refresh", { method: "POST" }),
};
