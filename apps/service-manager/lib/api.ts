/** service-manager API 客户端。
 *
 * 所有请求都走 /api/services/*（dev 由 next rewrites 代理，生产由 nginx 直转）。
 * 认证靠 HttpOnly cookie；前端从不持有口令或 Token。
 */

export const API = "/api/services";

export type RuntimeState = "running" | "partial" | "stopped" | "missing" | "unknown";
export type HealthState =
  | "healthy"
  | "unhealthy"
  | "starting"
  | "not_configured"
  | "unknown";
export type UrlState =
  | "reachable"
  | "auth_required"
  | "unexpected_status"
  | "unreachable"
  | "unknown";
export type TlsState = "valid" | "expiring" | "expired" | "invalid" | "unknown";
export type ReleaseState =
  | "unread"
  | "no_unread"
  | "no_releases"
  | "error"
  | "not_configured";
export type CheckStatus = "never" | "success" | "error";
export type EndpointKind = "internal" | "external" | "admin";
export type JobState =
  | "queued"
  | "running"
  | "completed"
  | "partial_failed"
  | "failed"
  | "interrupted";
export type RefreshKind = "docker" | "url" | "tls" | "releases" | "all";

/** 列表页用到的状态：只保留**运行**与**健康**两个维度。

 * URL / 证书 / 发布三个维度随入口与发布维护下线而不再展示（后端仍在检查，
 * 见 .trellis/spec/backend/service-manager/backend/index.md）。
 */
export interface ServiceStatus {
  runtime: RuntimeState;
  health: HealthState;
  component_states: Record<string, string>;
}

export interface ComposeFileView {
  raw: string;
  resolved: string | null;
  path_state: "absolute" | "relative_resolved" | "relative_unknown";
}

export interface MountView {
  kind: "bind" | "volume" | "tmpfs" | "other";
  source: string;
  destination: string;
  read_only: boolean;
}

export interface PortView {
  host_ip: string;
  host_port: number | null;
  container_port: number | null;
  protocol: "tcp" | "udp";
  address_family: "ipv4" | "ipv6";
  network_mode: string;
  kind: "published" | "exposed" | "historical" | "host_network";
  source: "docker" | "manual";
}

/** 写操作（新建 / 改标签 / 改名称用途）之后前端要用到的字段。 */
export interface ServicePatchResult {
  id: string;
  name: string;
  description: string;
  tags: string[];
  revision: number;
}

export interface ServiceListItem {
  id: string;
  name: string;
  description: string;
  tags: string[];
  revision: number;
  updated_at: string;
  primary_url: string | null;
  component_count: number;
  /** 该服务包含的 compose 项目（来源信息，不再决定分组） */
  projects: string[];
  status: ServiceStatus;
}

export interface DiscoveryCandidate {
  source_key: string;
  project: string | null;
  service_name: string | null;
  container_name: string;
  container_id: string;
  image_ref: string;
  state: string;
  health: HealthState;
  network_mode: string;
  ports: PortView[];
  compose_working_dir: string | null;
  compose_files: ComposeFileView[];
  ignored: boolean;
  oneoff: boolean;
  bindable: boolean;
  bound_service_id: string | null;
}

export interface DiscoveryResponse {
  items: DiscoveryCandidate[];
  docker_available: boolean;
  docker_error: string | null;
  last_success_at: string | null;
  projects: string[];
}

export interface PortOverviewRow extends PortView {
  source_key: string | null;
  container_name: string;
  project: string | null;
  service_id: string | null;
  service_name: string | null;
  note: string;
  origin: "docker" | "manual";
}

export interface PortOverviewResponse {
  items: PortOverviewRow[];
  overlaps: { left: string; right: string }[];
  scope_note: string;
}

export interface SummaryResponse {
  services: number;
  components: number;
  /** 上次扫描观测到的容器总数 */
  docker_components: number;
  /** 其中正在运行的 */
  docker_running: number;
  /** 其中已消失（成功扫描里没出现）的 */
  docker_missing: number;
  /** 发现但没关联到任何业务服务的容器 */
  unregistered_components: number;
  /** 未入账里被标记忽略的（有意不入账） */
  ignored_components: number;
  docker_available: boolean;
  docker_error: string | null;
  docker_last_success_at: string | null;
  counts: Record<string, Record<string, number>>;
  /** 全库标签词表：筛选栏的候选来源 */
  all_tags: string[];
  unread_releases: number;
  registry_revision: number;
  checker_heartbeat: string | null;
  /** 「我自己开发的」compose 项目名（列表据此分 tab） */
}

export interface RefreshJobView {
  id: string;
  kind: RefreshKind;
  target_id: string | null;
  state: JobState;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  counts: Record<string, number>;
  error: string | null;
  deduplicated: boolean;
}

export class ApiError extends Error {
  code: string;
  status: number;
  fieldErrors: Record<string, string>;

  constructor(status: number, code: string, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init.headers || {}),
    },
  });
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(
      response.status,
      data?.code ?? "error",
      data?.message ?? `请求失败（${response.status}）`,
      data?.field_errors ?? {},
    );
  }
  return data as T;
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  // 会话
  session: () => request<{ authenticated: boolean; expires_at: string | null }>("/auth/session"),
  login: (password: string) =>
    request<{ authenticated: boolean }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => request<{ authenticated: boolean }>("/auth/logout", { method: "POST" }),

  // 汇总
  summary: () => request<SummaryResponse>("/summary"),

  // 服务台账
  listServices: (params: {
    query?: string;
    tag?: string;
    page?: number;
    page_size?: number;
  }) =>
    request<{ items: ServiceListItem[]; total: number; page: number; page_size: number }>(
      `/services${query(params)}`,
    ),
  createService: (body: Record<string, unknown>) =>
    request<ServicePatchResult>("/services", { method: "POST", body: JSON.stringify(body) }),
  patchService: (id: string, body: Record<string, unknown>) =>
    request<ServicePatchResult>(`/services/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteService: (id: string) =>
    request<{ deleted: string }>(`/services/${id}`, { method: "DELETE" }),

  // 入口
  deleteReleaseSource: (serviceId: string) =>
    request<{ ok: boolean }>(`/services/${serviceId}/release-source`, { method: "DELETE" }),
  discovery: (params: {
    project?: string;
    state?: string;
    ignored?: boolean | null;
    include_ephemeral?: boolean;
  }) => request<DiscoveryResponse>(`/discovery${query(params)}`),
  importComponents: (body: Record<string, unknown>) =>
    request<{ service_id: string; created: boolean; bound: string[]; registry_revision: number }>(
      "/discovery/import",
      { method: "POST", body: JSON.stringify(body) },
    ),
  setIgnored: (sourceKeys: string[], ignored: boolean) =>
    request<{ registry_revision: number; updated: number }>("/discovery/decisions", {
      method: "PATCH",
      body: JSON.stringify({ source_keys: sourceKeys, ignored }),
    }),

  // 资源
  ports: (params: { only_registered?: boolean; query?: string; protocol?: string }) =>
    request<PortOverviewResponse>(`/resources/ports${query(params)}`),
  refresh: (kind: RefreshKind, targetId?: string | null) =>
    request<RefreshJobView>("/refresh", {
      method: "POST",
      body: JSON.stringify({ kind, target_id: targetId ?? null }),
    }),
  job: (jobId: string) => request<RefreshJobView>(`/jobs/${jobId}`),
  jobs: () => request<{ items: RefreshJobView[] }>("/jobs"),

  // 备份
  exportBackup: () => request<Record<string, unknown>>("/backup/export"),
  previewBackup: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{
      digest: string;
      registry_revision: number;
      counts: Record<string, number>;
      current_counts: Record<string, number>;
      warnings: string[];
    }>("/backup/preview", { method: "POST", body });
  },
  restoreBackup: (file: File, digest: string, registryRevision: number) => {
    const body = new FormData();
    body.append("file", file);
    body.append("digest", digest);
    body.append("registry_revision", String(registryRevision));
    body.append("confirm", "true");
    return request<{
      restored: Record<string, number>;
      backup_path: string;
      registry_revision: number;
    }>("/backup/restore", { method: "POST", body });
  },
};

export function downloadBackup(payload: Record<string, unknown>): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "service-manager-backup.json";
  anchor.click();
  URL.revokeObjectURL(url);
}
