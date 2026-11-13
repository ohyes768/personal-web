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

export interface CheckView {
  check_kind: string;
  check_status: CheckStatus;
  current_state: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  error_code: string | null;
  error_message: string | null;
  next_due_at: string | null;
  stale: boolean;
  payload: Record<string, unknown> | null;
}

export interface ServiceStatus {
  runtime: RuntimeState;
  health: HealthState;
  url: UrlState;
  tls: TlsState;
  release: ReleaseState;
  url_check: CheckView | null;
  tls_check: CheckView | null;
  release_check: CheckView | null;
  unread_releases: number;
  primary_url: string | null;
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

export interface ComponentView {
  source_key: string;
  project: string | null;
  service_name: string | null;
  container_name: string;
  container_id: string;
  image_ref: string;
  image_id: string;
  state: string;
  health: HealthState;
  network_mode: string;
  ports: PortView[];
  mounts: MountView[];
  compose_working_dir: string | null;
  compose_files: ComposeFileView[];
  data_paths: string[];
  last_seen_at: string | null;
  present: boolean;
  required: boolean;
  label: string;
  override_source: "docker" | "manual";
}

export interface RouteTarget {
  component_source_key: string | null;
  scheme: "http" | "https";
  host: string;
  port: number | null;
  path_prefix: string;
  note: string;
}

export interface EndpointRecord {
  id: string;
  service_id: string;
  label: string;
  kind: EndpointKind;
  url: string;
  probe_url: string | null;
  enabled: boolean;
  expected_status_ranges: string[];
  tls_check: boolean;
  route_target: RouteTarget | null;
  renewal_note: string;
  revision: number;
}

export interface PortNoteRecord {
  id: string;
  service_id: string;
  host_ip: string;
  host_port: number;
  container_port: number | null;
  protocol: "tcp" | "udp";
  note: string;
  revision: number;
}

export interface ReleaseSourceRecord {
  id: string;
  service_id: string;
  owner: string;
  repo: string;
  installed_tag_note: string;
  revision: number;
}

export interface ServiceListItem {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  revision: number;
  updated_at: string;
  primary_url: string | null;
  component_count: number;
  /** 该服务包含的 compose 项目（自己开发的 vs 其他，用来分 tab） */
  projects: string[];
  status: ServiceStatus;
}

export interface ServiceDetail {
  id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  notes: string;
  revision: number;
  created_at: string;
  updated_at: string;
  components: ComponentView[];
  endpoints: EndpointRecord[];
  port_notes: PortNoteRecord[];
  release_source: ReleaseSourceRecord | null;
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

export interface DomainOverviewRow {
  host: string;
  scheme: string;
  port: number | null;
  path: string;
  url: string;
  endpoint_id: string;
  endpoint_label: string;
  endpoint_kind: EndpointKind;
  service_id: string;
  service_name: string;
  route_target: RouteTarget | null;
  tls_state: TlsState;
  tls_days_remaining: number | null;
  /** 证书无效的原因（self_signed 等） */
  tls_invalid_reason: string | null;
  is_ip: boolean;
}

export interface CertificateOverviewRow {
  host: string;
  port: number;
  tls_state: TlsState;
  subject: string;
  issuer: string;
  sans: string[];
  not_before: string | null;
  not_after: string | null;
  days_remaining: number | null;
  fingerprint: string;
  used_by: string[];
  error: string | null;
  invalid_reason: string | null;
}

export interface ReleaseView {
  owner: string;
  repo: string;
  release_id: number;
  tag: string;
  name: string;
  published_at: string | null;
  body: string;
  html_url: string;
  read: boolean;
}

export interface ReleaseListResponse {
  source: ReleaseSourceRecord | null;
  items: ReleaseView[];
  check: CheckView | null;
  truncated: boolean;
  latest_release_id: number | null;
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
  unread_releases: number;
  registry_revision: number;
  checker_heartbeat: string | null;
  /** 「我自己开发的」compose 项目名（列表据此分 tab） */
  own_projects: string[];
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
    category?: string;
    tag?: string;
    page?: number;
    page_size?: number;
  }) =>
    request<{ items: ServiceListItem[]; total: number; page: number; page_size: number }>(
      `/services${query(params)}`,
    ),
  getService: (id: string) => request<ServiceDetail>(`/services/${id}`),
  createService: (body: Record<string, unknown>) =>
    request<ServiceDetail>("/services", { method: "POST", body: JSON.stringify(body) }),
  patchService: (id: string, body: Record<string, unknown>) =>
    request<ServiceDetail>(`/services/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteService: (id: string) =>
    request<{ deleted: string }>(`/services/${id}`, { method: "DELETE" }),

  // 入口
  addEndpoint: (serviceId: string, body: Record<string, unknown>) =>
    request<EndpointRecord>(`/services/${serviceId}/endpoints`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateEndpoint: (serviceId: string, endpointId: string, body: Record<string, unknown>) =>
    request<EndpointRecord>(`/services/${serviceId}/endpoints/${endpointId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteEndpoint: (serviceId: string, endpointId: string) =>
    request<{ ok: boolean }>(`/services/${serviceId}/endpoints/${endpointId}`, {
      method: "DELETE",
    }),

  // 手工端口
  addPortNote: (serviceId: string, body: Record<string, unknown>) =>
    request<PortNoteRecord>(`/services/${serviceId}/port-notes`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deletePortNote: (serviceId: string, noteId: string) =>
    request<{ ok: boolean }>(`/services/${serviceId}/port-notes/${noteId}`, {
      method: "DELETE",
    }),

  // 组件
  setComponentRequired: (serviceId: string, sourceKey: string, required: boolean) =>
    request<{ ok: boolean }>(
      `/services/${serviceId}/components/${encodeURIComponent(sourceKey)}/required${query({ required })}`,
      { method: "POST" },
    ),
  unbindComponent: (serviceId: string, sourceKey: string) =>
    request<{ ok: boolean }>(
      `/services/${serviceId}/components/${encodeURIComponent(sourceKey)}`,
      { method: "DELETE" },
    ),
  setOverride: (sourceKey: string, body: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/components/${encodeURIComponent(sourceKey)}/override`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  // GitHub 仓库
  setReleaseSource: (serviceId: string, body: Record<string, unknown>) =>
    request<ReleaseSourceRecord>(`/services/${serviceId}/release-source`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteReleaseSource: (serviceId: string) =>
    request<{ ok: boolean }>(`/services/${serviceId}/release-source`, { method: "DELETE" }),
  listReleases: (serviceId: string) =>
    request<ReleaseListResponse>(`/services/${serviceId}/releases`),
  markReleasesRead: (serviceId: string, releaseIds: number[]) =>
    request<{ updated: number }>(`/services/${serviceId}/releases/read`, {
      method: "POST",
      body: JSON.stringify({ release_ids: releaseIds }),
    }),

  // 发现
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
  domains: (params: { query?: string }) =>
    request<{ items: DomainOverviewRow[] }>(`/resources/domains${query(params)}`),
  certificates: (params: { query?: string }) =>
    request<{ items: CertificateOverviewRow[] }>(`/resources/certificates${query(params)}`),

  // 刷新
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
