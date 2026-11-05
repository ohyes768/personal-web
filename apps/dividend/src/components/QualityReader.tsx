/**
 * 基本面资料阅读页（独立路由 /quality-reader）
 *
 * URL 的 code 参数是当前公司的唯一身份：
 * - 翻篇用 History API pushState 同步 query，保留浏览器真实 pathname（线上带 /dividend 前缀）；
 * - 当前公司从 useSearchParams 与本地快照派生，不另存选中下标；
 * - 主动换篇回到正文顶部并聚焦标题，刷新资料不抢焦点、不重置滚动。
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { QualityReportContent } from './QualityReportContent';
import { useQualityReports } from '@/lib/hooks/useQualityReports';
import { returnHref, selectReport, sortReports } from '@/lib/quality-reader';

export function QualityReader() {
  const { snapshot, loading, refreshing, error, refresh } = useQualityReports();
  const searchParams = useSearchParams();
  const codeParam = searchParams.get('code');

  const [pathname, setPathname] = useState<string>('');
  const titleRef = useRef<HTMLHeadingElement>(null);
  const pendingFocus = useRef<string | null>(null);
  const canonicalized = useRef(false);

  useEffect(() => {
    setPathname(window.location.pathname);
  }, []);

  const reports = useMemo(() => sortReports(snapshot?.scores), [snapshot]);
  const reportsRef = useRef(reports);
  reportsRef.current = reports;

  const current = useMemo(() => selectReport(reports, codeParam), [reports, codeParam]);
  const index = current ? reports.findIndex(report => report.code === current.code) : -1;

  /** 用浏览器真实 pathname 拼当前页 query（保留 fromTab/fromFav，清掉 hash） */
  const buildUrl = useCallback((code: string | null) => {
    const params = new URLSearchParams(window.location.search);
    if (code === null) params.delete('code');
    else params.set('code', code);
    const query = params.toString();
    return `${window.location.pathname}${query ? `?${query}` : ''}`;
  }, []);

  /** 首次加载成功且地址里没有 code 时，把第一篇的代码写回地址（不打断阅读） */
  useEffect(() => {
    if (canonicalized.current) return;
    if (codeParam !== null) return;
    if (!reports.length) return;
    canonicalized.current = true;
    window.history.replaceState(null, '', buildUrl(reports[0].code));
  }, [buildUrl, codeParam, reports]);

  /** 主动换篇：更新地址并回到正文顶部、聚焦标题 */
  const switchTo = useCallback((code: string) => {
    pendingFocus.current = code;
    window.history.pushState(null, '', buildUrl(code));
  }, [buildUrl]);

  /** 上下篇按点击瞬间的地址计算，连续快速点击不会停在同一篇 */
  const step = useCallback((delta: number) => {
    const list = reportsRef.current;
    if (!list.length) return;
    const params = new URLSearchParams(window.location.search);
    const currentCode = params.get('code');
    const found = currentCode === null ? -1 : list.findIndex(report => report.code === currentCode);
    const from = found >= 0 ? found : (delta > 0 ? -1 : 0);
    const target = list[from + delta];
    if (target) switchTo(target.code);
  }, [switchTo]);

  useEffect(() => {
    if (!codeParam || pendingFocus.current !== codeParam) return;
    pendingFocus.current = null;
    window.scrollTo({ top: 0, behavior: 'auto' });
    titleRef.current?.focus();
  }, [codeParam]);

  const backHref = pathname ? returnHref(pathname, new URLSearchParams(searchParams.toString())) : './';
  const screeningHref = pathname
    ? returnHref(pathname, new URLSearchParams('fromTab=screening'))
    : './?tab=screening';

  const prev = index > 0 ? reports[index - 1] : null;
  const next = index >= 0 && index < reports.length - 1 ? reports[index + 1] : null;
  const progress = index >= 0 ? `第 ${index + 1} / ${reports.length} 篇` : `共 ${reports.length} 篇`;

  const showFatalError = !!error && !snapshot;
  const showEmpty = !loading && !showFatalError && !!snapshot && reports.length === 0;
  const showMissing = !loading && !showFatalError && !!snapshot && reports.length > 0 && codeParam !== null && !current;
  const showContent = !loading && !showFatalError && !!snapshot && reports.length > 0 && (codeParam === null || !!current);

  return (
    <div className="quality-reader-root">
      <div className="quality-reader-container">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <a href={backHref} className="quality-reader-link">← 返回股息率</a>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="quality-reader-btn quality-reader-btn-ghost"
          >
            {refreshing ? '刷新中…' : '刷新资料'}
          </button>
        </div>

        <h1 className="quality-reader-title">基本面资料阅读</h1>

        {/* 不做公司下拉筛选：固定展示地址 code 指定的公司，翻篇只走上一篇/下一篇 */}
        <div className="quality-reader-controls">
          <span className="quality-reader-progress" aria-live="polite">{progress}</span>
        </div>

        {loading && !snapshot && (
          <p className="quality-reader-state" role="status">正在加载基本面资料…</p>
        )}

        {showFatalError && (
          <div className="quality-reader-state quality-reader-error" role="alert">
            <p>基本面资料加载失败：{error}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="quality-reader-btn" onClick={() => void refresh()}>重试</button>
              <a href={backHref} className="quality-reader-link">← 返回股息率</a>
            </div>
          </div>
        )}

        {showEmpty && (
          <div className="quality-reader-state">
            <p>暂无基本面资料；请在选股关注完成分析后再来阅读。</p>
            <a href={screeningHref} className="quality-reader-link mt-3 inline-block">返回选股关注</a>
          </div>
        )}

        {showMissing && (
          <div className="quality-reader-state">
            <p>该公司的基本面资料暂不可用。</p>
            <a href={backHref} className="quality-reader-link mt-3 inline-block">← 返回股息率</a>
          </div>
        )}

        {error && snapshot && (
          <p className="quality-reader-refresh-error" role="alert">
            刷新失败，继续显示上次加载的资料：{error}
          </p>
        )}

        {showContent && current && (
          <article className="quality-reader-article">
            <h2 ref={titleRef} tabIndex={-1} className="quality-reader-company">{current.name}</h2>
            <p className="quality-reader-code">{current.code}</p>
            <QualityReportContent score={current} currentSkillVersion={snapshot?.current_skill_version} />
          </article>
        )}
      </div>

      <nav className="quality-reader-nav" aria-label="报告翻页">
        <div className="quality-reader-nav-inner">
          <button
            type="button"
            className="quality-reader-btn"
            disabled={!prev}
            onClick={() => step(-1)}
          >
            上一篇
          </button>
          <span className="quality-reader-progress">{progress}</span>
          <button
            type="button"
            className="quality-reader-btn"
            disabled={!next}
            onClick={() => step(1)}
          >
            下一篇
          </button>
        </div>
      </nav>
    </div>
  );
}
