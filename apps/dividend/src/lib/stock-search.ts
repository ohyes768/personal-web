/**
 * 股息率「全部」页股票搜索的纯函数工具
 *
 * 语义与后端 `GET /api/dividend/stocks?search=` 一致：
 * - 关键词去掉首尾空格；空串 = 未搜索（后端按原筛选链路返回）
 * - 命中范围是**完整收集池**，不受股息率阈值限制
 * - codes（只看收藏）与搜索结果取交集
 */

/**
 * 关键词归一：去掉首尾空格；空串表示未搜索。
 */
export function normalizeSearchKeyword(raw: string): string {
  return raw.trim();
}

/**
 * 构造搜索请求参数。
 *
 * @param keyword 原始输入（内部归一）
 * @param codes 逗号分隔的代码集合；undefined = 不限范围，'' = 限定为空集合
 *               （「只看收藏」且收藏为空时传 ''，不能传 undefined——那会变成全池搜索）
 */
export function buildStockSearchParams(keyword: string, codes?: string): {
  search: string;
  min_yield: number;
  sort_by: string;
  sort_order: 'desc';
  codes?: string;
} {
  const normalized = normalizeSearchKeyword(keyword);
  const params: {
    search: string;
    min_yield: number;
    sort_by: string;
    sort_order: 'desc';
    codes?: string;
  } = {
    search: normalized,
    min_yield: 0,
    sort_by: 'avg_yield_3y',
    sort_order: 'desc',
  };
  const trimmedCodes = codes?.trim();
  if (trimmedCodes) params.codes = trimmedCodes;
  return params;
}
