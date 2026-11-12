/** 状态文案与配色（design §6 / §8：颜色外辅以文字，不抹平维度）。 */

import type {
  CheckView,
  HealthState,
  ReleaseState,
  RuntimeState,
  TlsState,
  UrlState,
} from "./api";

export interface Tone {
  /** 语义色，用于 badge 背景 */
  tone: "ok" | "warn" | "bad" | "muted" | "info";
  label: string;
}

export const RUNTIME: Record<RuntimeState, Tone> = {
  running: { tone: "ok", label: "运行中" },
  partial: { tone: "warn", label: "部分运行" },
  stopped: { tone: "muted", label: "已停止" },
  missing: { tone: "bad", label: "已消失" },
  unknown: { tone: "muted", label: "未登记组件" },
};

export const HEALTH: Record<HealthState, Tone> = {
  healthy: { tone: "ok", label: "健康" },
  unhealthy: { tone: "bad", label: "不健康" },
  starting: { tone: "warn", label: "启动中" },
  // 没配健康检查 → 这个维度对本服务不适用，显示 "-"。
  // 不要求使用者去维护它；有自我检查的组件照常显示真实状态。
  not_configured: { tone: "muted", label: "-" },
  unknown: { tone: "muted", label: "未知" },
};

export const URL_STATE: Record<UrlState, Tone> = {
  reachable: { tone: "ok", label: "可达" },
  auth_required: { tone: "warn", label: "需认证" },
  unexpected_status: { tone: "warn", label: "状态异常" },
  unreachable: { tone: "bad", label: "不可达" },
  unknown: { tone: "muted", label: "未检查" },
};

export const TLS_STATE: Record<TlsState, Tone> = {
  valid: { tone: "ok", label: "有效" },
  expiring: { tone: "warn", label: "即将到期" },
  expired: { tone: "bad", label: "已过期" },
  invalid: { tone: "bad", label: "无效" },
  unknown: { tone: "muted", label: "未检查" },
};

export const RELEASE_STATE: Record<ReleaseState, Tone> = {
  unread: { tone: "info", label: "有新版本" },
  no_unread: { tone: "ok", label: "无未读" },
  no_releases: { tone: "muted", label: "暂无正式发布" },
  error: { tone: "bad", label: "检查失败" },
  not_configured: { tone: "muted", label: "未关联仓库" },
};

export const JOB_STATE: Record<string, Tone> = {
  queued: { tone: "muted", label: "排队中" },
  running: { tone: "info", label: "运行中" },
  completed: { tone: "ok", label: "完成" },
  partial_failed: { tone: "warn", label: "部分失败" },
  failed: { tone: "bad", label: "失败" },
  interrupted: { tone: "warn", label: "已中断" },
};

/** 汇总页「异常」判定：任一维度落在 bad/warn 且不是「未检查」。 */
export function abnormalTones(status: {
  runtime: RuntimeState;
  health: HealthState;
  url: UrlState;
  tls: TlsState;
  release: ReleaseState;
}): Tone[] {
  const tones = [
    RUNTIME[status.runtime],
    HEALTH[status.health],
    URL_STATE[status.url],
    TLS_STATE[status.tls],
    RELEASE_STATE[status.release],
  ];
  return tones.filter((item) => item.tone === "bad" || item.tone === "warn");
}

/** 时间显示：统一按 Asia/Shanghai，并标出陈旧数据。 */
export function formatTime(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatRelative(value: string | null): string {
  if (!value) return "从未";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const diffMs = Date.now() - parsed.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}

/** 检查结果的一行说明：区分「本次请求失败」与「观测到的异常」。 */
export function describeCheck(check: CheckView | null, fallback = "未检查"): string {
  if (!check) return fallback;
  const when = formatRelative(check.last_attempt_at);
  if (check.check_status === "never") return "未检查";
  if (check.check_status === "error") {
    const lastOk = check.last_success_at
      ? `（上次成功 ${formatRelative(check.last_success_at)}）`
      : "";
    return `${when}检查失败：${check.error_message ?? check.error_code ?? "未知错误"}${lastOk}`;
  }
  if (check.stale) {
    return `${when}（数据已陈旧）`;
  }
  return when;
}

export function portKindLabel(kind: string): string {
  switch (kind) {
    case "published":
      return "宿主映射";
    case "exposed":
      return "容器内部";
    case "historical":
      return "历史映射";
    case "host_network":
      return "宿主网络";
    default:
      return kind;
  }
}

export function portText(port: {
  host_ip: string;
  host_port: number | null;
  container_port: number | null;
  protocol: string;
}): string {
  const container = port.container_port ?? "?";
  if (port.host_port === null) {
    return `${container}/${port.protocol}（仅容器内）`;
  }
  return `${port.host_ip || "0.0.0.0"}:${port.host_port} → ${container}/${port.protocol}`;
}

export function composeFileText(file: {
  raw: string;
  resolved: string | null;
  path_state: string;
}): string {
  if (file.path_state === "relative_unknown") {
    return `${file.raw}（相对路径，位置未确认）`;
  }
  return file.resolved ?? file.raw;
}

/** 证书 invalid 的原因说明：自签/域名不符/链过期/不受信。 */
export function tlsInvalidReason(reason: string | null | undefined): string {
  switch (reason) {
    case "self_signed":
      return "自签证书（不是签发机构签发）";
    case "hostname_mismatch":
      return "证书与访问的域名不匹配";
    case "expired_chain":
      return "证书链已过期";
    case "untrusted_ca":
      return "签发机构不在信任列表";
    case "unknown":
      return "验证未通过";
    default:
      return "";
  }
}

/**
 * 证书徽章的 tooltip：说清楚「为什么无效」和「什么时候到期」，
 * 别只丢一个红灯让人猜。
 */
export function tlsTooltip(check: CheckView | null): string {
  const when = describeCheck(check);
  if (!check?.payload) return when;
  const reason = tlsInvalidReason(
    typeof check.payload.invalid_reason === "string" ? check.payload.invalid_reason : "",
  );
  const notAfter =
    typeof check.payload.not_after === "string" ? check.payload.not_after : "";
  const bits = [reason, notAfter ? `有效期至 ${notAfter.slice(0, 10)}` : ""].filter(
    Boolean,
  );
  return bits.length ? `${bits.join(" · ")} · ${when}` : when;
}

/** 健康徽章的 tooltip：说明覆盖了多少个组件，避免「1/2 组件报了健康」被误读。 */
export function healthTooltip(
  components: { health: HealthState }[] | undefined,
  state: HealthState,
): string {
  if (state === "not_configured") {
    return "该服务没有组件配置 Docker 健康检查，此维度不适用（显示 -）";
  }
  if (!components || components.length === 0) return "Docker 健康检查";
  const configured = components.filter((c) => c.health !== "not_configured").length;
  if (configured < components.length) {
    return `Docker 健康检查：${configured}/${components.length} 个组件配置了检查`;
  }
  return "Docker 健康检查";
}

/**
 * 台账分组：属于「我自己开发的」compose 项目 = 自己那组，其余算其他。
 *
 * 还没关联容器的服务（多半是人工登记的）先归自己这组，关联后按 compose
 * 项目自动归位；只有容器、没有 compose 标签的（如 nas:container:*）算其他。
 */
export function isOwnService(
  item: { projects: string[]; component_count: number },
  ownProjects: string[],
): boolean {
  if (ownProjects.length === 0) return false;
  if (item.component_count === 0) return true;
  return item.projects.some((project) => ownProjects.includes(project));
}
