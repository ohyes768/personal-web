// 缺失地块轮廓:生成 → 预览 → 人工确认 → 撤销 的契约与请求封装。
//
// 后端接口全部公开(无需登录),但只接受小区 ID / 候选 ID / 版本号 / 操作 ID,
// 几何一律来自服务端保存的候选,浏览器不提交任何坐标。

export type BoundaryJobPhase =
  | 'queued' | 'reading' | 'fetching' | 'estimating'
  | 'succeeded' | 'failed' | 'interrupted';

export type BoundaryCandidateStatus =
  | 'ready' | 'applied' | 'rejected' | 'superseded' | 'stale' | 'reverted';

export interface BoundaryReferenceBuilding {
  kind: 'building' | 'residential';
  rings: number[][][]; // GCJ-02: [环][点][lng,lat]
}

export interface BoundaryCandidate {
  candidate_id: string;
  job_id: string;
  community_id: string;
  community_name: string;
  status: BoundaryCandidateStatus;
  rings: number[][][];
  reference_buildings: BoundaryReferenceBuilding[];
  area_ha: number | null;
  building_faces: number;
  residential_faces: number;
  low_confidence: boolean;
  source: string;
  warnings: string[];
  estimated_at: string | null;
  created_at: string;
  revision: string;
  stale: boolean;
  stale_reasons: string[];
  applicable: boolean;
  position: [number, number] | null;
}

export interface BoundaryJob {
  job_id: string;
  community_id: string;
  phase: BoundaryJobPhase;
  error_code: string | null;
  error_message: string | null;
  candidate_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface BoundaryOverride {
  candidate_id: string;
  confirmed_at: string;
  revision: number;
  source: string;
}

export interface BoundaryRevertable {
  operation_id: string;
  candidate_id: string;
  confirmed_at: string;
}

export interface BoundaryWorkflowState {
  community_id: string;
  community_name: string;
  position: [number, number];
  revision: string;
  has_visible_boundary: boolean;
  boundary_source: string | null;
  boundary_confirmed_at: string | null;
  base_has_boundary: boolean;
  override: BoundaryOverride | null;
  job: { job_id: string; phase: BoundaryJobPhase; created_at: string; updated_at: string } | null;
  latest_job: { job_id: string; phase: BoundaryJobPhase; error_code: string | null; error_message: string | null; created_at: string } | null;
  candidate: { candidate_id: string; status: BoundaryCandidateStatus; area_ha: number | null; low_confidence: boolean; created_at: string } | null;
  revertable: BoundaryRevertable | null;
}

export interface BoundaryEstimateAccepted {
  job_id: string;
  phase: BoundaryJobPhase;
  candidate_id?: string | null;
  reused: boolean;
}

export class BoundaryWorkflowError extends Error {
  code: string;
  status: number;
  constructor(message: string, code = 'unknown', status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function errorMessage(payload: unknown, fallback: string): { message: string; code: string } {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === 'object') {
    const record = detail as { message?: unknown; code?: unknown };
    if (typeof record.message === 'string') {
      return { message: record.message, code: typeof record.code === 'string' ? record.code : 'unknown' };
    }
  }
  if (typeof detail === 'string' && detail) return { message: detail, code: 'unknown' };
  return { message: fallback, code: 'unknown' };
}

export async function boundaryRequest<T>(
  path: string,
  method: 'GET' | 'POST' = 'GET',
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`/api/map${path}`, {
    method,
    signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const { message, code } = errorMessage(payload, '轮廓操作暂时不可用');
    throw new BoundaryWorkflowError(message, code, response.status);
  }
  if (!payload || payload.success !== true || !('data' in payload)) {
    throw new BoundaryWorkflowError('轮廓接口响应异常', 'bad_response', response.status);
  }
  return payload.data as T;
}

export const boundaryPaths = {
  workflow: (cid: string) => `/communities/${cid}/boundary-workflow`,
  estimates: (cid: string) => `/communities/${cid}/boundary-estimates`,
  job: (jobId: string) => `/boundary-estimates/${jobId}`,
  candidate: (candidateId: string) => `/boundary-candidates/${candidateId}`,
  reject: (candidateId: string) => `/boundary-candidates/${candidateId}/reject`,
  apply: (candidateId: string) => `/boundary-candidates/${candidateId}/apply`,
  revert: (cid: string) => `/communities/${cid}/boundary-reverts`,
};

// --- 展示层纯函数 -----------------------------------------------------------

export const BOUNDARY_PHASE_LABELS: Record<BoundaryJobPhase, string> = {
  queued: '等待处理',
  reading: '读取建筑数据',
  fetching: '联网获取建筑',
  estimating: '估算轮廓',
  succeeded: '已生成候选',
  failed: '生成失败',
  interrupted: '任务中断',
};

export const BOUNDARY_ERROR_MESSAGES: Record<string, string> = {
  timeout: '请求建筑数据超时,网络繁忙时可以稍后重试',
  network: '获取建筑数据失败,所有镜像均不可达,请稍后重试',
  rate_limited: '建筑数据服务限流,请过一会儿再试',
  no_geometry: '该定位附近没有可用的建筑数据',
  invalid_geometry: '生成的轮廓未通过几何校验,已拒绝保存',
  interrupted: '服务重启导致任务中断,可以手动重新生成',
  stale: '小区状态已变化,任务已作废',
  internal: '生成过程出错,请稍后重试',
};

export function boundaryPhaseLabel(phase: string | null | undefined): string {
  if (!phase) return '未知状态';
  return BOUNDARY_PHASE_LABELS[phase as BoundaryJobPhase] ?? phase;
}

export function boundaryErrorText(code: string | null | undefined, fallback?: string | null): string {
  if (code && BOUNDARY_ERROR_MESSAGES[code]) return BOUNDARY_ERROR_MESSAGES[code];
  if (fallback) return fallback;
  return '生成失败,请稍后重试';
}

// 参考面数量:住宅用地面与建筑面分开说,不一律叫"楼栋"
export function boundaryReferenceSummary(candidate: BoundaryCandidate): string {
  const building = candidate.building_faces ?? 0;
  const residential = candidate.residential_faces ?? 0;
  if (building && residential) return `${building} 个建筑面 + ${residential} 个住宅面`;
  if (residential) return `${residential} 个住宅用地面`;
  if (building) return `${building} 个建筑面`;
  return '无参考面记录';
}

export function boundaryAreaText(areaHa: number | null | undefined): string {
  if (areaHa == null) return '面积未知';
  return `${areaHa.toFixed(2)} 公顷`;
}

export function isBoundaryJobActive(phase: string | null | undefined): boolean {
  return phase === 'queued' || phase === 'reading' || phase === 'fetching' || phase === 'estimating';
}

export function newOperationId(): string {
  const globalCrypto = typeof window !== 'undefined' ? window.crypto : undefined;
  if (globalCrypto && typeof globalCrypto.randomUUID === 'function') return globalCrypto.randomUUID();
  return `op-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * 判断是不是工作流错误。
 *
 * 不只靠 instanceof: 转译到 ES5 时 Error 子类的 instanceof 会失效,模块被重复加载时
 * 也会失效。按 (message, code) 的形状判断更稳。
 */
export function isBoundaryWorkflowError(value: unknown): value is BoundaryWorkflowError {
  if (value instanceof BoundaryWorkflowError) return true;
  if (!value || typeof value !== 'object') return false;
  const record = value as { message?: unknown; code?: unknown };
  return typeof record.message === 'string' && typeof record.code === 'string';
}

/**
 * 异步动作的统一生命周期: 开始置忙, 结束(成功或失败)一定复位。
 *
 * busy 若不复位, 界面上的按钮会一直 disabled —— 点下去毫无反应, 用户看不出原因。
 * 收在一处实现, 就不可能再漏掉某一条成功路径的复位。
 */
export async function runBoundaryAction(
  action: () => Promise<void>,
  handlers: { busy: () => void; settle: (error: string | null) => void },
  fallbackMessage = '操作失败,请重试',
): Promise<void> {
  handlers.busy();
  try {
    await action();
    handlers.settle(null);
  } catch (err) {
    handlers.settle(isBoundaryWorkflowError(err) ? err.message : fallbackMessage);
  }
}
