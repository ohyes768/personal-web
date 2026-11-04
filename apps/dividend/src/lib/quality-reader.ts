/**
 * 基本面资料阅读页的纯函数工具：阅读集合排序、当前公司选择、路径前缀与页面链接
 *
 * 纯工具文件：不引入运行时别名（仅 import type），便于用 node 原生 TS 单测直接引入。
 * 线上部署形态：应用 basePath 为空，nginx 用 `location /dividend/` + `proxy_pass .../` 剥前缀，
 * 因此浏览器地址带 /dividend 而应用内路径不带；这里统一按浏览器真实 pathname 判定。
 */
import type { QualityScore } from '@/lib/quality';

/** 阅读页可回跳的主页面视图 */
export type ReaderSourceTab = 'all' | 'alerts' | 'screening';

/** 阅读集合排序：按六位股票代码升序（稳定，翻篇顺序不随刷新变化） */
export function sortReports(scores: Record<string, QualityScore> | null | undefined): QualityScore[] {
  return Object.values(scores ?? {}).sort((a, b) => a.code.localeCompare(b.code));
}

/**
 * 选出当前公司：
 * - code 为 null（地址里没有 code 参数）时默认第一篇；
 * - code 非空但集合里找不到（非法或已删除）时返回 null，由页面显示「暂不可用」，不静默换成别家。
 */
export function selectReport(reports: QualityScore[], code: string | null): QualityScore | null {
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
 * 主页面 → 阅读页链接。
 * sourceQuery 是主页面当前 query（tab / fav）；只保留有效参数，忽略任意 returnUrl。
 * fav 只在「全部」视图下有意义。
 */
export function readerHref(pathname: string, sourceQuery: URLSearchParams): string {
  const prefix = getDividendPrefix(pathname);
  const rawTab = sourceQuery.get('tab');
  const fav = sourceQuery.get('fav') === '1' || rawTab === 'watchlist';
  const tab = normalizeSourceTab(rawTab);
  const params = new URLSearchParams();
  if (tab === 'all') {
    if (fav) {
      params.set('fromTab', 'all');
      params.set('fromFav', '1');
    }
  } else {
    params.set('fromTab', tab);
  }
  const query = params.toString();
  return `${prefix}/quality-reader${query ? `?${query}` : ''}`;
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
