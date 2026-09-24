/**
 * 前端数据模型：与 backend/skill-manager/src/models.py 一一对应（design 7）。
 * 字段保持后端 snake_case，避免两层命名映射漂移。
 */

export type SkillSource = 'local' | 'github';
export type TargetKey = 'openclaw' | 'hermes';
export type PlanAction = 'add' | 'update' | 'unchanged' | 'blocked';

/** models.TargetDeployment */
export interface TargetDeployment {
  status: string;
  revision: string;
  published_at: string;
  link_target: string;
  /** 账实核对：账本 active 但目标链接不存在；真实动作以计划预览为准 */
  link_missing: boolean;
}

/** models.UpdateInfo */
export interface UpdateInfo {
  skill_id: string;
  repository: string;
  remote_revision: string;
  remote_tags: string[];
  cached_revision: string;
  has_update: boolean;
  checked_at: string;
}

/** models.SkillCard */
export interface SkillCard {
  id: string;
  name: string;
  source: SkillSource;
  path: string;
  repository: string | null;
  tags: string[];
  summary: string;
  status: string;
  deployments: Record<string, TargetDeployment>;
  update: UpdateInfo | null;
  /** 本环境 GitHub 缓存目录缺失（local 来源恒 false）；true 时需先 Clone */
  cache_missing: boolean;
  /** 本环境源库中登记目录缺失（github 来源恒 false）；true 时提示源缺失 */
  source_missing: boolean;
}

/** models.SkillListResponse */
export interface SkillListResponse {
  items: SkillCard[];
}

/** models.ScanResponse */
export interface ScanCandidate {
  path: string;
}

export interface ScanResponse {
  repository: string;
  candidates: ScanCandidate[];
}

/** models.UpdateCheckResponse */
export interface UpdateCheckItem {
  skill_id: string;
  result: 'ok' | 'error';
  info: UpdateInfo | null;
  error: string;
}

export interface UpdateCheckResponse {
  items: UpdateCheckItem[];
}

/** models.PlanItem / PlanResponse */
export interface PlanItem {
  skill_id: string;
  target: TargetKey;
  action: PlanAction;
  reason: string;
  current_revision: string;
  planned_revision: string;
}

export interface PlanResponse {
  items: PlanItem[];
}

/** models.PublishResultItem / PublishBatchResult */
export interface PublishResultItem {
  skill_id: string;
  target: TargetKey;
  status: 'success' | 'blocked' | 'error';
  action: 'add' | 'update' | 'rollback' | 'none';
  error: string;
}

export interface PublishBatchResult {
  items: PublishResultItem[];
}

/** models.UnpublishResponse */
export interface UnpublishResponse {
  skill_id: string;
  target: TargetKey;
  status: 'removed';
}

/** models.UpdateSkillTagsResponse：单卡标签全量替换结果 */
export interface UpdateSkillTagsResponse {
  skill_id: string;
  tags: string[];
}

/** 请求体 */
export interface QueueItemRequest {
  skill_id: string;
  targets: TargetKey[];
}

export interface RegisterGithubSkillInput {
  repository: string;
  path: string;
  name: string;
  tags: string[];
  summary: string;
}

/** 统一错误契约：routes.py 的 detail {"code","message","item_id"?} */
export interface ApiError {
  code: string;
  message: string;
  item_id?: string;
}
