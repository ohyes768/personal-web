/**
 * 前端数据模型：与 backend/skill-manager/src/models.py 一一对应（design 7）。
 * 字段保持后端 snake_case，避免两层命名映射漂移。
 */

export type SkillSource = 'local' | 'github';
export interface ExportTarget {
  id: string;
  name: string;
  install_path: string;
  notes: string;
  enabled: boolean;
  deployment_count: number;
}
export type ExportTargetInput = Omit<ExportTarget, 'deployment_count'>;
import type { LinkTargetKey } from './targets';
export type { TargetKey } from './targets';
export type PlanAction = 'add' | 'update' | 'unchanged' | 'blocked';

/** models.TargetDeployment */
export interface TargetDeployment {
  status: string;
  revision: string;
  published_at: string;
  link_target: string;
  /** 账实核对：账本 active 但目标链接不存在；真实动作以计划预览为准 */
  link_missing: boolean;
  stale: boolean;
  content_hash: string;
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

/** models.TaskKind / TaskState：GitHub 后台任务（PRD R1-R4） */
export type TaskKind = 'scan' | 'register' | 'register_batch' | 'clone_cache';
export type TaskState = 'running' | 'done' | 'error';

/** models.ScanCandidate：扫描候选目录（含 SKILL.md frontmatter 元数据） */
export interface ScanCandidate {
  path: string;
  name: string;
  description: string;
}

/** models.ScanTopLevelEntry：仓库根顶层清单项（随行共享资源勾选依据） */
export interface ScanTopLevelEntry {
  path: string;
  is_dir: boolean;
}

/** models.RegisterBatchResultItem：批量登记任务逐项成败（部分成功语义） */
export interface RegisterBatchResultItem {
  skill_id: string;
  status: 'success' | 'error';
  error: string;
}

/** models.AsyncTaskCreatedResponse：clone 类操作已转后台任务，202 返回 */
export interface AsyncTaskCreated {
  task_id: string;
  kind: TaskKind;
}

/** models.TaskSnapshot：GET /api/skills/github/tasks/{task_id} 的轮询快照。
 * candidates/top_level/referenced_paths 仅 scan 任务 state=done 时非空；
 * results 仅 register_batch 任务非空（running 中可见已处理项）；
 * error_* 仅 state=error 时非空 */
export interface TaskSnapshot {
  task_id: string;
  kind: TaskKind;
  repository: string;
  skill_id: string | null;
  state: TaskState;
  /** remote_check / negotiating / receiving / resolving / discover / registry */
  stage: string;
  progress_percent: number | null;
  progress_detail: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  candidates: ScanCandidate[];
  top_level: ScanTopLevelEntry[];
  referenced_paths: string[];
  results: RegisterBatchResultItem[];
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
  target: LinkTargetKey;
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
  target: LinkTargetKey;
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
  target: LinkTargetKey;
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
  targets: LinkTargetKey[];
}

export interface RegisterGithubSkillInput {
  repository: string;
  path: string;
  name: string;
  tags: string[];
  summary: string;
  /** 随行共享资源（仓库根相对路径）：发布时拷进 staging 快照 */
  shared_paths: string[];
}

/** models.GithubRegisterItem：批量登记的单项候选 */
export interface GithubRegisterItem {
  path: string;
  name: string;
  tags: string[];
  summary: string;
}

/** models.RegisterGithubBatchRequest：一次登记同一仓库的多个候选目录 */
export interface RegisterGithubBatchInput {
  repository: string;
  /** 整批共享的随行资源（合集仓库根级共享资源通常不随候选变化） */
  shared_paths: string[];
  items: GithubRegisterItem[];
}

/** 统一错误契约：routes.py 的 detail {"code","message","item_id"?} */
export interface ApiError {
  code: string;
  message: string;
  item_id?: string;
}
