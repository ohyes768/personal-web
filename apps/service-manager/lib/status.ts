/** 状态文案与配色（design §6 / §8：颜色外辅以文字，不抹平维度）。 */

import type { HealthState, RuntimeState } from "./api";

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

