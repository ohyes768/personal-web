/**
 * 估值资料阅读页的纯函数工具：阅读集合排序、当前公司选择、路径前缀与页面链接
 *
 * 与 lib/quality-reader.ts 同构（同一套线上前缀约定）：
 * 线上部署形态：应用 basePath 为空，nginx 用 `location /dividend/` + `proxy_pass .../` 剥前缀，
 * 因此浏览器地址带 /dividend 而应用内路径不带；这里统一按浏览器真实 pathname 判定。
 *
 * 本文件刻意不 import 任何运行时模块（只用 import type）：
 * node --experimental-strip-types 解析无扩展名的相对导入会失败，
 * 而本文件要能被 node --test 直接跑（见 valuation-reader.test.ts）。
 * 线上前缀判定与 quality-reader.ts 保持同一份口径，各写一份避免引入运行时依赖。
 */
import type { ValuationReportRecord } from './valuation';

/** 阅读页可回跳的主页面视图 */
export type ReaderSourceTab = 'all' | 'alerts' | 'screening';

/** 阅读集合排序：按六位股票代码升序（稳定，翻篇顺序不随刷新变化） */
export function sortReports(
  reports: Record<string, ValuationReportRecord> | null | undefined,
): ValuationReportRecord[] {
  return Object.values(reports ?? {}).sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * 选出当前公司：
 * - code 为 null（地址里没有 code 参数）时默认第一篇；
 * - code 非空但集合里找不到（非法或已删除）时返回 null，由页面显示「暂不可用」，不静默换成别家。
 */
export function selectReport(
  reports: ValuationReportRecord[],
  code: string | null,
): ValuationReportRecord | null {
  if (!reports.length) return null;
  if (code === null) return reports[0];
  return reports.find(report => report.code === code) ?? null;
}

/** 线上前缀判定：只有 /dividend 或 /dividend/ 开头才算线上，/dividend-other/ 不算 */
export function getDividendPrefix(pathname: string): '' | '/dividend' {
  return /^\/dividend(?:\/|$)/.test(pathname) ? '/dividend' : '';
}

/** 主页面 tab 参数归一化：旧的 watchlist 等价于「全部 + 只看收藏」 */
export function normalizeSourceTab(tab: string | null): ReaderSourceTab {
  if (tab === 'alerts') return 'alerts';
  if (tab === 'screening') return 'screening';
  return 'all';
}

/**
 * 主页面 → 阅读页链接（不指定股票，阅读页自己落到第一篇）。
 * sourceQuery 是主页面当前 query（tab / fav）；只保留有效参数，忽略任意 returnUrl。
 */
export function readerHref(pathname: string, sourceQuery: URLSearchParams): string {
  return buildReaderHref(pathname, sourceQuery, null);
}

/**
 * 主页面 → 阅读页链接（指定某只股票）。
 * 收藏跟踪行内的「查看报告」用它，直接落到那一份报告。
 */
export function reportHref(pathname: string, code: string, sourceQuery: URLSearchParams): string {
  return buildReaderHref(pathname, sourceQuery, code);
}

function buildReaderHref(pathname: string, sourceQuery: URLSearchParams, code: string | null): string {
  const prefix = getDividendPrefix(pathname);
  const rawTab = sourceQuery.get('tab');
  const fav = sourceQuery.get('fav') === '1' || rawTab === 'watchlist';
  const tab = normalizeSourceTab(rawTab);
  const params = new URLSearchParams();
  if (code) params.set('code', code);
  if (tab === 'all') {
    if (fav) {
      params.set('fromTab', 'all');
      params.set('fromFav', '1');
    }
  } else {
    params.set('fromTab', tab);
  }
  const query = params.toString();
  return `${prefix}/valuation-reader${query ? `?${query}` : ''}`;
}

/** 阅读页 → 主页面链接：回到进入前的视图（只保留有效的 tab / fav） */
export function returnHref(pathname: string, readerQuery: URLSearchParams): string {
  const prefix = getDividendPrefix(pathname);
  const tab = normalizeSourceTab(readerQuery.get('fromTab'));
  const fav = readerQuery.get('fromFav') === '1';
  const params = new URLSearchParams();
  if (tab !== 'all') params.set('tab', tab);
  if (tab === 'all' && fav) params.set('fav', '1');
  const query = params.toString();
  return `${prefix}/${query ? `?${query}` : ''}`;
}
