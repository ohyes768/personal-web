/** 状态文案与配色（design §6 / §8：颜色外辅以文字，不抹平维度）。 */

import type { HealthState, RuntimeState, TlsState } from "./api";

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


export const TLS_STATE: Record<TlsState, Tone> = {
  valid: { tone: "ok", label: "有效" },
  expiring: { tone: "warn", label: "即将到期" },
  expired: { tone: "bad", label: "已过期" },
  invalid: { tone: "bad", label: "无效" },
  unknown: { tone: "muted", label: "未检查" },
};

/** 证书无效的原因：说清楚「为什么无效」，别只丢一个红灯让人猜。 */
export function tlsInvalidReason(reason: string | null | undefined): string {
  switch (reason) {
    case "self_signed":
      return "自签证书：没有公共机构背书，浏览器会先警告";
    case "hostname_mismatch":
      return "证书上的域名和访问的域名对不上";
    case "expired_chain":
      return "证书链已过期";
    case "untrusted_ca":
      return "签发机构不在系统信任列表里";
    case "unknown":
      return "验证没通过";
    default:
      return "";
  }
}

/**
 * 证书徽章：一个笼统的「无效」会让人以为证书坏了。
 * 自签与「不受信」是**警告**（证书能用，但客户端会拦一下），
 * 域名不符和链过期才是真的坏（红）。
 */
export function tlsTone(state: TlsState, invalidReason?: string | null): Tone {
  const base = TLS_STATE[state] ?? TLS_STATE.unknown;
  if (state !== "invalid") return base;
  switch (invalidReason) {
    case "self_signed":
      return { tone: "warn", label: "自签" };
    case "untrusted_ca":
      return { tone: "warn", label: "不受信任" };
    case "hostname_mismatch":
      return { tone: "bad", label: "域名不符" };
    case "expired_chain":
      return { tone: "bad", label: "链已过期" };
    default:
      return base;
  }
}

/** 证书 tooltip：为什么无效 + 什么时候到期 + 还剩几天。 */
export function tlsEndpointTooltip(info: {
  tls_state: string;
  tls_days_remaining: number | null;
  tls_not_after: string | null;
  tls_invalid_reason: string | null;
}): string {
  const state = (info.tls_state || "unknown") as TlsState;
  const bits: string[] = [];
  const reason = tlsInvalidReason(info.tls_invalid_reason);
  if (reason) bits.push(reason);
  if (info.tls_not_after) bits.push(`有效期至 ${info.tls_not_after.slice(0, 10)}`);
  if (info.tls_days_remaining !== null && info.tls_days_remaining >= 0) {
    bits.push(`还剩 ${info.tls_days_remaining} 天`);
  }
  const base = TLS_STATE[state]?.label ?? "未检查";
  return bits.length ? `${base} · ${bits.join(" · ")}` : base;
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

