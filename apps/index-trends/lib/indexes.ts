/** 指数选项：后端 `src/core/indexes.py` 的注册表镜像。
 *
 * 只用于渲染切换器与标题；真实数据一律按 code 从接口取，
 * 新增指数时两处一起改（backend 注册 + 这里一行）。
 */
export const INDEX_OPTIONS = [
  { code: "000300", name: "沪深300", hasTrend: true },
  // 创业板50 只做 PB/PE 分位：没有走势通道，页面不渲染通道标签页
  { code: "399673", name: "创业板50", hasTrend: false },
] as const;

export type IndexCode = (typeof INDEX_OPTIONS)[number]["code"];

export const DEFAULT_INDEX_CODE: IndexCode = "000300";

export function indexName(code: string): string {
  return INDEX_OPTIONS.find((item) => item.code === code)?.name ?? code;
}

export function isIndexCode(value: string | null): value is IndexCode {
  return !!value && INDEX_OPTIONS.some((item) => item.code === value);
}

export function hasTrend(code: string): boolean {
  return INDEX_OPTIONS.find((item) => item.code === code)?.hasTrend ?? true;
}
