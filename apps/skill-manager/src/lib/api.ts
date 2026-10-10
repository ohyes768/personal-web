/**
 * 唯一前端 API 客户端（design 7）。
 *
 * - 只调用受控后端端点；调用方只能传 id/target/queue 等白名单字段；
 * - 写操作密码仅随本次请求体传输，客户端不做任何持久化；
 * - 错误统一解析为 {code, message}，HTTP 非 2xx 抛 ApiClientError。
 */
import type {
  ApiError,
  AsyncTaskCreated,
  PlanResponse,
  PublishBatchResult,
  QueueItemRequest,
  RegisterGithubBatchInput,
  RegisterGithubSkillInput,
  SkillListResponse,
  TargetKey,
  TaskSnapshot,
  UnpublishResponse,
  UpdateCheckResponse,
  UpdateSkillTagsResponse,
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

async function request<T>(path: string, init?: RequestInit, base = BASE): Promise<T> {
  const response = await fetch(`${base}${path}`, {
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

const TARGET_BASE = '/api/export-targets';
export const listExportTargets = () => request<{ items: import('./types').ExportTarget[] }>('', undefined, TARGET_BASE);
export const createExportTarget = (input: import('./types').ExportTargetInput) => request<import('./types').ExportTarget>('', { method: 'POST', body: JSON.stringify(input) }, TARGET_BASE);
export const updateExportTarget = (id: string, input: Partial<Omit<import('./types').ExportTargetInput, 'id'>>) => request<import('./types').ExportTarget>(`/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) }, TARGET_BASE);
export const deleteExportTarget = (id: string) => request<{ id: string }>(`/${encodeURIComponent(id)}`, { method: 'DELETE' }, TARGET_BASE);

function jsonBody(payload: unknown): string {
  return JSON.stringify(payload);
}

export async function exportSkill(skillId: string, target: import('./targets').ExportTargetKey): Promise<void> {
  const response = await fetch(`${BASE}/${encodeURIComponent(skillId)}/export`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: jsonBody({ target }),
  });
  if (!response.ok) throw new ApiClientError(await parseErrorBody(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1] ?? `${skillId}.zip`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function deleteExport(skillId: string, target: import('./targets').ExportTargetKey): Promise<unknown> {
  return request(`/${encodeURIComponent(skillId)}/exports/${target}`, { method: 'DELETE' });
}

// ---------- 公开只读端点 ----------

export function listSkills(): Promise<SkillListResponse> {
  return request<SkillListResponse>('');
}

/** 发起后台扫描任务（PRD R1）：可达性预检失败同步 400，可达返回 202 任务 */
export function startGithubScan(repository: string): Promise<AsyncTaskCreated> {
  return request<AsyncTaskCreated>('/github/scan', {
    method: 'POST',
    body: jsonBody({ repository }),
  });
}

/** 轮询 GitHub 后台任务快照（PRD R4）；不存在/已回收 404 task_not_found */
export function getGithubTask(taskId: string): Promise<TaskSnapshot> {
  return request<TaskSnapshot>(`/github/tasks/${encodeURIComponent(taskId)}`);
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

/** 登记候选目录（PRD R2）：密码/预检同步校验，clone 与入库在后台任务执行 */
export function registerGithubSkill(
  input: RegisterGithubSkillInput,
  password: string
): Promise<AsyncTaskCreated> {
  return request<AsyncTaskCreated>('/github', {
    method: 'POST',
    body: jsonBody({ ...input, password }),
  });
}

/** 批量登记同一仓库的多个候选目录（design §5.2）：仓库级 clone 一次，
 * 逐项成败经任务快照 results 表达（部分成功语义） */
export function registerGithubBatch(
  input: RegisterGithubBatchInput,
  password: string
): Promise<AsyncTaskCreated> {
  return request<AsyncTaskCreated>('/github/batch', {
    method: 'POST',
    body: jsonBody({ ...input, password }),
  });
}

/** 重建缺失的 GitHub 缓存（PRD R3）：clone 在后台任务执行 */
export function cloneGithubCache(
  skillId: string,
  password: string
): Promise<AsyncTaskCreated> {
  return request<AsyncTaskCreated>(
    `/github/${encodeURIComponent(skillId)}/clone`,
    {
      method: 'POST',
      body: jsonBody({ password }),
    }
  );
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

export function deleteSkill(
  skillId: string,
  password: string
): Promise<{ skill_id: string }> {
  return request<{ skill_id: string }>(`/${encodeURIComponent(skillId)}`, {
    method: 'DELETE',
    body: jsonBody({ password }),
  });
}

export function updateSkillTags(
  skillId: string,
  tags: string[]
): Promise<UpdateSkillTagsResponse> {
  return request<UpdateSkillTagsResponse>(
    `/${encodeURIComponent(skillId)}/tags`,
    {
      method: 'PATCH',
      body: jsonBody({ tags }),
    }
  );
}
