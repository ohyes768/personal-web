/**
 * 唯一前端 API 客户端（design 7）。
 *
 * - 只调用受控后端端点；调用方只能传 id/target/queue 等白名单字段；
 * - 写操作密码仅随本次请求体传输，客户端不做任何持久化；
 * - 错误统一解析为 {code, message}，HTTP 非 2xx 抛 ApiClientError。
 */
import type {
  ApiError,
  PlanResponse,
  PublishBatchResult,
  QueueItemRequest,
  RegisterGithubSkillInput,
  ScanResponse,
  SkillListResponse,
  TargetKey,
  UnpublishResponse,
  UpdateCheckResponse,
} from './types';

const BASE = '/api/skills';

export class ApiClientError extends Error {
  readonly code: string;
  readonly itemId?: string;

  constructor(err: ApiError) {
    super(err.message);
    this.name = 'ApiClientError';
    this.code = err.code;
    this.itemId = err.item_id;
  }
}

async function parseErrorBody(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json();
    // main.py 的 exception handler 把契约对象展平到顶层 {"code","message"}；
    // 兼容读取顶层字段与 FastAPI 默认的 detail 包装两种形态
    for (const candidate of [
      body,
      (body as { detail?: unknown })?.detail,
    ]) {
      if (candidate && typeof candidate === 'object') {
        const d = candidate as { code?: unknown; message?: unknown; item_id?: unknown };
        if (typeof d.message === 'string') {
          return {
            code: typeof d.code === 'string' ? d.code : 'http_error',
            message: d.message,
            item_id: typeof d.item_id === 'string' ? d.item_id : undefined,
          };
        }
      }
    }
    const detail = (body as { detail?: unknown })?.detail;
    if (detail !== undefined && detail !== null) {
      return { code: 'http_error', message: String(detail) };
    }
  } catch {
    // 响应体不是 JSON，走通用错误
  }
  return { code: `http_${response.status}`, message: `请求失败（HTTP ${response.status}）` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw new ApiClientError(await parseErrorBody(response));
  }
  return (await response.json()) as T;
}

function jsonBody(payload: unknown): string {
  return JSON.stringify(payload);
}

// ---------- 公开只读端点 ----------

export function listSkills(): Promise<SkillListResponse> {
  return request<SkillListResponse>('');
}

export function scanGithubRepository(repository: string): Promise<ScanResponse> {
  return request<ScanResponse>('/github/scan', {
    method: 'POST',
    body: jsonBody({ repository }),
  });
}

export function checkUpdates(skillIds: string[] = []): Promise<UpdateCheckResponse> {
  return request<UpdateCheckResponse>('/check-updates', {
    method: 'POST',
    body: jsonBody({ skill_ids: skillIds }),
  });
}

export function publishPlan(items: QueueItemRequest[]): Promise<PlanResponse> {
  return request<PlanResponse>('/publish/plan', {
    method: 'POST',
    body: jsonBody({ items }),
  });
}

// ---------- 密码保护端点 ----------

export function registerGithubSkill(
  input: RegisterGithubSkillInput,
  password: string
): Promise<{ id: string }> {
  return request<{ id: string }>('/github', {
    method: 'POST',
    body: jsonBody({ ...input, password }),
  });
}

export function publish(
  items: QueueItemRequest[],
  password: string
): Promise<PublishBatchResult> {
  return request<PublishBatchResult>('/publish', {
    method: 'POST',
    body: jsonBody({ items, password }),
  });
}

export function rollbackSkill(
  skillId: string,
  target: TargetKey,
  password: string
): Promise<unknown> {
  return request<unknown>(`/${encodeURIComponent(skillId)}/targets/${target}/rollback`, {
    method: 'POST',
    body: jsonBody({ password }),
  });
}

export function unpublishSkill(
  skillId: string,
  target: TargetKey,
  password: string
): Promise<UnpublishResponse> {
  return request<UnpublishResponse>(`/${encodeURIComponent(skillId)}/targets/${target}`, {
    method: 'DELETE',
    body: jsonBody({ password }),
  });
}
