/** 幸福里来源探查：只点击与选择，不接受用户粘贴的链接。 */

export interface ProbeCandidate {
  candidate_id: string;
  neighborhood_id: string;
  name: string;
  address: string;
  longitude: number | null;
  latitude: number | null;
  coordinate_system: string;
  phase: string;
  rent_total: number | null;
  discovered_via: string;
  homepage_url: string;
  evidence: string[];
  evidence_gaps: string[];
  conflicts: string[];
  strong: boolean;
}

export interface ProbeState {
  stage: string;
  revision: number;
  running: boolean;
  message?: string;
  community_id?: string;
  candidates?: ProbeCandidate[] | null;
  selected_page?: ProbeCandidate | null;
}

export const PROBE_STAGES = {
  idle: '尚未探查',
  searching_homepage: '正在查找幸福里小区主页',
  needs_homepage_selection: '请选择对应的小区主页',
  resolving_entry: '正在寻找该主页的租房入口',
  bound_pending_collection: '已关联幸福里来源，等待下一轮采集',
  homepage_not_found: '未找到幸福里小区主页',
  entry_not_found: '该主页没有可用的租房入口',
  upstream_failed: '幸福里暂时无法访问',
  cooling_down: '幸福里请求冷却中',
  deferred: '本轮请求额度已用完',
  cancelled: '探查已取消',
  interrupted: '探查被中断',
} as const;

const RUNNING_STAGES = new Set(['searching_homepage', 'resolving_entry']);

export function probeStageLabel(stage: string | undefined): string {
  if (!stage) return PROBE_STAGES.idle;
  return (PROBE_STAGES as Record<string, string>)[stage] ?? stage;
}

export function probeIsRunning(stage: string | undefined): boolean {
  return !!stage && RUNNING_STAGES.has(stage);
}

export function probePath(communityId: string) {
  return `/api/map/communities/${encodeURIComponent(communityId)}/rental-source/probe`;
}

export async function probeRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json();
  if (!response.ok || payload.success !== true) {
    throw new Error(typeof payload.detail === 'string' ? payload.detail : '租金来源探查暂时不可用，请重试');
  }
  return payload.data as T;
}
