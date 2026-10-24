export type IntegrationState = {
  phase?: string;
  tags_updated?: number;
  device_published?: boolean;
  metadata_errors?: {title: string; message: string}[];
  ma?: {status: string; message?: string};
};

type Generation = {status: string; error?: string | null; integration?: IntegrationState};
type Presentation = {tone: "info" | "success" | "warning"; message: string};

export function describeGeneration(generation?: Generation): Presentation | null {
  if (!generation || generation.status === "idle") return null;
  if (generation.status === "failed") return {tone: "warning", message: generation.error || "生成失败，请重新生成"};
  const state = generation.integration;
  if (generation.status === "running") {
    if (state?.phase === "syncing") {
      return {tone: "info", message: state.ma?.message || (state.ma?.status === "verifying"
        ? "MA 扫描完成，正在核对所选专辑的曲目…" : "设备歌单已生成，正在同步 MA…")};
    }
    return {tone: "info", message: `正在校验并补齐音频信息${state?.tags_updated ? `，已更新 ${state.tags_updated} 首` : ""}…`};
  }
  if (state?.ma?.status === "ready") return {tone: "success", message: "设备歌单已生成，MA 已就绪。"};
  if (state?.ma?.status === "failed" || state?.ma?.status === "not_configured") {
    return {tone: "warning", message: `设备歌单已生成；${state.ma.message || "MA 尚未就绪，请重新生成重试。"}`};
  }
  return {tone: "info", message: "设备歌单已生成；尚无 MA 就绪记录，可重新生成并同步。"};
}
