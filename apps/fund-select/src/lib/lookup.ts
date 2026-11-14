/**
 * 基金代码查询（GET /api/funds/lookup/{code}）
 *
 * - 后端返回该代码应去哪个 tab + 完整跳转 path（相对路径）
 * - 前端只做输入归一化与错误分类，不自己拼 tab 判定
 * - fetch 必须写全路径 /funds/api/...（原生 fetch 不吃 basePath）
 */
'use client';

/** 后端 FundLookupResponse 对齐（7 字段） */
export interface FundLookup {
  code: string;
  found: boolean;
  name: string | null;
  /** bond|stock|discovery-bond|discovery-stock；not found 时为 null */
  tab: string | null;
  market_type: string | null;
  /** 命中哪份精选名单：'bond'|'stock'|null */
  in_yaml: string | null;
  /** 完整跳转路径（相对，不含 /funds 前缀）；not found 时为 null */
  path: string | null;
}

/** 全角数字 → 半角 */
function toHalfWidth(s: string): string {
  return s.replace(/[０-９]/g, ch =>
    String.fromCharCode(ch.charCodeAt(0) - 0xfee0));
}

/**
 * 输入归一化：trim + 全角转半角 + 只保留数字，然后要求恰好 6 位。
 * 不足/超出/含字母 → null（调用方据此禁用提交）。
 */
export function normalizeCode(input: string): string | null {
  const digits = toHalfWidth(input.trim()).replace(/\D/g, '');
  return digits.length === 6 ? digits : null;
}

/** 查询该代码属于哪个 tab；网络/HTTP 失败抛出，业务未命中返回 found=false */
export async function fetchFundLookup(
  code: string,
  signal?: AbortSignal,
): Promise<FundLookup> {
  const res = await fetch(`/funds/api/funds/lookup/${code}`, {
    cache: 'no-store',
    signal,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`查询失败 ${res.status}: ${detail.slice(0, 120)}`);
  }
  return (await res.json()) as FundLookup;
}

/** 检索结果状态分类（UI 分支用） */
export type LookupPhase = 'idle' | 'loading' | 'found' | 'not-found' | 'error';

export function classifyLookup(
  result: FundLookup | null,
  error: string | null,
): LookupPhase {
  if (error !== null) return 'error';
  if (result === null) return 'idle';
  return result.found && result.path ? 'found' : 'not-found';
}
