/**
 * 代码搜索态（11-16-fund-code-search-list-result）
 *
 * 契约：URL 参数 `search_code=<6 位>` = 列表锁定单只基金。
 * - 与筛选参数**并存**：搜索态不清任何筛选维度，退出后原筛选原样回来
 * - 与 `?code=` **正交**：`code=` 是「直达并自动开抽屉」（经理页徽章），
 *   `search_code=` 是「列表里只显示这一只、点行才开抽屉」
 * - 值不合法（非 6 位数字）视为「无搜索」——URL 手改坏了不该白屏
 *
 * 纯函数模块：不 import React，可被 node --experimental-strip-types --test 直接跑。
 */

/** 全角数字 → 半角（与 lib/lookup.ts 同口径，两处各留一份避免组件依赖纯逻辑） */
function toHalfWidth(s: string): string {
  return s.replace(/[０-９]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0xfee0));
}

export const SEARCH_CODE_PARAM = 'search_code';

/**
 * URL 值 → 合法代码（6 位数字）；非法/缺失一律 null。
 *
 * - 全角数字归一（用户从聊天工具里复制常见全角）
 * - 只接受「恰好 6 位数字」：`002 910` / `002-910` 这种带分隔符的**不**接受，
 *   因为 URL 里的值是机器写的（搜索框已经在提交前归一过了），
 *   宽松解析只会把 `12345` 这类半截代码悄悄当成搜索态
 */
export function parseSearchCode(raw: string | null | undefined): string | null {
  if (raw == null) return null;
  const v = toHalfWidth(raw.trim());
  return /^\d{6}$/.test(v) ? v : null;
}

/** 合法的搜索态 → 写进 URL 查询串；null/非法 → 空串（不写参数） */
export function searchCodeToParam(code: string | null | undefined): string {
  return parseSearchCode(code) ?? '';
}

/**
 * 代码搜索落点 URL（前端拼，不用后端 path 原样 push）。
 *
 * 为什么不能直接用后端返回的 `path`：它是 `/<page>?search_code=xxx`，
 * 直接 router.push 会把当前筛选参数整串丢掉——用户明明筛着规模 ≥ 5 亿，
 * 搜完回来筛选没了（实测踩到）。
 *
 * 规则：
 * - **同页**（在当前 tab 上搜到本 tab 的基金，pathname 后缀相同）：
 *   保留当前查询串，仅替换 `search_code` 并把 page 归 1。
 * - **跨页**（搜到的基金在另一个 tab）：只带 `search_code`。
 *   两个 tab 的筛选维度虽然同名，但用户在那个页面上并没有设过，
 *   把一堆筛选悄悄搬过去反而莫名。
 *
 * 返回值**不含 basePath**（Next Link/router 会自动补，写 /funds/... 会 404）。
 */
export function buildSearchHref(
  targetPath: string,
  currentSearch: string,
  currentPathname: string,
): string {
  const qIndex = targetPath.indexOf('?');
  const targetPage = qIndex === -1 ? targetPath : targetPath.slice(0, qIndex);
  const targetQuery = qIndex === -1 ? '' : targetPath.slice(qIndex + 1);

  const targetParams = new URLSearchParams(targetQuery);
  const searchCode = targetParams.get(SEARCH_CODE_PARAM);
  if (searchCode === null) return targetPath;  // 非搜索落点：原样返回

  // 同页判定：pathname 含 basePath（/funds/stock），目标页是 /stock
  const samePage = currentPathname.replace(/\/$/, '').endsWith(targetPage);

  const params = new URLSearchParams(samePage ? currentSearch.replace(/^\?/, '') : '');
  params.delete('code');        // ?code= 是「直达开抽屉」，与搜索态互斥
  params.delete('focus');       // 旧代码搜索遗留参数，已废弃
  params.delete('search_code');
  params.set(SEARCH_CODE_PARAM, searchCode);
  params.delete('page');        // 搜索结果只有 1 条，回到第 1 页
  return `${targetPage}?${params.toString()}`;
}

/**
 * 搜索态 → 后端查询参数。
 *
 * 关键：搜索态**只发 code**，不带任何阈值参数——后端在搜索短路里也会忽略它们，
 * 这里不拼是为了让网络面板里的请求能直接看出「这是搜索，不是筛选」。
 *
 * 非搜索态返回 null，调用方据此走原本的筛选拼装逻辑。
 */
export function searchCodeApiQuery(code: string | null | undefined): string | null {
  const valid = parseSearchCode(code);
  return valid === null ? null : `code=${valid}`;
}
