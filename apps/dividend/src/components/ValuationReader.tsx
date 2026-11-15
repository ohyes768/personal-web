/**
 * 估值资料阅读页（独立路由 /valuation-reader）
 *
 * URL 的 code 参数是当前公司的唯一身份：
 * - 翻篇用 History API pushState 同步 query，保留浏览器真实 pathname（线上带 /dividend 前缀）；
 * - 当前公司从 useSearchParams 与本地快照派生，不另存选中下标；
 * - 主动换篇回到正文顶部并聚焦标题，刷新资料不抢焦点、不重置滚动。
 *
 * 与 /quality-reader 同构：同一套阅读动线（返回 / 刷新 / 下拉选股 / 上一篇下一篇）。
 * 估值报告只有这一个阅读入口（弹窗已删除），避免两套渲染走偏。
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ValuationReportContent } from './ValuationReportContent';
import { ValuationApplyConfirm } from './ValuationApplyConfirm';
import { useAlertsStatus } from '@/lib/hooks/useAlertsStatus';
import { useRealtimePrices } from '@/lib/hooks/useRealtimePrices';
import { useValuation } from '@/lib/hooks/useValuation';
import { dividendApi } from '@/lib/api';
import { isReportNewerThanAlerts } from '@/lib/valuation';
import { returnHref, selectReport, sortReports } from '@/lib/valuation-reader';

export function ValuationReader() {
  const { reports, currentSkillVersion, loading, analyze, refresh } = useValuation();
  const alertsStatus = useAlertsStatus();
  const searchParams = useSearchParams();
  const codeParam = searchParams.get('code');

  const [pathname, setPathname] = useState<string>('');
  const [applyOpen, setApplyOpen] = useState(false);
  const [applyPending, setApplyPending] = useState(false);
  const [applyError, setApplyError] = useState('');
  const [notice, setNotice] = useState('');
  const titleRef = useRef<HTMLHeadingElement>(null);
  const pendingFocus = useRef<string | null>(null);
  const canonicalized = useRef(false);

  useEffect(() => {
    setPathname(window.location.pathname);
  }, []);

  const reportsList = useMemo(() => sortReports(reports), [reports]);
  const reportsRef = useRef(reportsList);
  reportsRef.current = reportsList;

  const current = useMemo(() => selectReport(reportsList, codeParam), [reportsList, codeParam]);
  const index = current ? reportsList.findIndex(report => report.code === current.code) : -1;

  // 现价：只取当前这一只（应用确认卡要判断应用后落在哪一区）
  const { priceMap } = useRealtimePrices(current ? [current.code] : []);
  const currentPrice = current
    ? (priceMap.get(current.code)?.realtime ?? priceMap.get(current.code)?.close ?? null)
    : null;

  const alertItem = current ? alertsStatus.alertMap.get(current.code) : undefined;
  const effectiveLevels = alertItem?.levels ?? null;
  /** 这份报告是不是还没应用（比生效挡位新） */
  const pendingApply = current
    ? current.status === 'ready' && isReportNewerThanAlerts(current.evaluated_at, alertItem?.updated_at ?? null)
    : false;

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
    if (!reportsList.length) return;
    canonicalized.current = true;
    window.history.replaceState(null, '', buildUrl(reportsList[0].code));
  }, [buildUrl, codeParam, reportsList]);

  /** 主动换篇：更新地址并回到正文顶部、聚焦标题 */
  const switchTo = useCallback((code: string) => {
    pendingFocus.current = code;
    setNotice('');
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

  const prev = index > 0 ? reportsList[index - 1] : null;
  const next = index >= 0 && index < reportsList.length - 1 ? reportsList[index + 1] : null;
  const progress = index >= 0 ? `第 ${index + 1} / ${reportsList.length} 篇` : `共 ${reportsList.length} 篇`;

  const handleApply = useCallback(async () => {
    if (!current) return;
    setApplyError('');
    setApplyPending(true);
    try {
      await dividendApi.applyValuationReport(current.code, current.evaluated_at);
      await Promise.all([alertsStatus.refresh(), refresh()]);
      setNotice(`${current.name} 挡位已应用，监控已开启`);
      setApplyOpen(false);
    } catch (err) {
      setApplyError(err instanceof Error ? err.message : '应用失败，请重试');
    } finally {
      setApplyPending(false);
    }
  }, [alertsStatus, current, refresh]);

  const handleReevaluate = useCallback(async () => {
    if (!current) return;
    setNotice('');
    await analyze([current.code]);
  }, [analyze, current]);

  return (
    <div className="quality-reader-root">
      <div className="quality-reader-container">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <a href={backHref} className="quality-reader-link">← 返回股息率</a>
          <button
            type="button"
            onClick={() => void refresh()}
            className="quality-reader-btn quality-reader-btn-ghost"
          >
            刷新资料
          </button>
        </div>

        <h1 className="quality-reader-title">估值资料阅读</h1>

        {/* 公司选择器：下拉直接跳到指定股票，翻篇仍可走上一篇/下一篇 */}
        <div className="quality-reader-controls">
          <label className="quality-reader-select-label" htmlFor="valuation-reader-company-select">
            选择股票
          </label>
          <select
            id="valuation-reader-company-select"
            className="quality-reader-select"
            value={current?.code ?? ''}
            onChange={(event) => switchTo(event.target.value)}
            disabled={!reportsList.length}
          >
            {!reportsList.length && <option value="">加载中…</option>}
            {reportsList.map(report => (
              <option key={report.code} value={report.code}>
                {report.name}（{report.code}）{report.status === 'ready' ? '' : ' 未出价格'}
              </option>
            ))}
          </select>
          <span className="quality-reader-progress" aria-live="polite">{progress}</span>
        </div>

        {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}

        {loading && (
          <p className="quality-reader-state" role="status">正在加载估值资料…</p>
        )}

        {!loading && !reportsList.length && (
          <div className="quality-reader-state">
            <p>暂无估值报告；请在收藏跟踪完成四挡位评估后再来阅读。</p>
            <a href={backHref} className="quality-reader-link mt-3 inline-block">← 返回股息率</a>
          </div>
        )}

        {!loading && reportsList.length > 0 && codeParam !== null && !current && (
          <div className="quality-reader-state">
            <p>该公司的估值资料暂不可用。</p>
            <a href={backHref} className="quality-reader-link mt-3 inline-block">← 返回股息率</a>
          </div>
        )}

        {current && (
          <article className="quality-reader-article">
            <h2 ref={titleRef} tabIndex={-1} className="quality-reader-company">{current.name}</h2>
            <p className="quality-reader-code">{current.code}</p>

            {pendingApply && (
              <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                这份评估还没有应用；当前生效的仍是上一套挡位。
              </p>
            )}

            {/* 操作区：应用 / 再评估（会话下载在报告元数据行里） */}
            <div className="flex flex-wrap items-center gap-2">
              {current.status === 'ready' && (
                <button
                  type="button"
                  className="quality-reader-btn"
                  onClick={() => { setApplyError(''); setApplyOpen(true); }}
                >
                  {pendingApply ? '应用挡位' : '确认并应用挡位'}
                </button>
              )}
              <button
                type="button"
                className="quality-reader-btn quality-reader-btn-ghost"
                onClick={() => void handleReevaluate()}
              >
                重新评估
              </button>
            </div>

            <ValuationReportContent
              report={current}
              effectiveLevels={effectiveLevels}
              currentSkillVersion={currentSkillVersion}
            />
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

      {/* 应用确认：新旧四档对比 + 应用后落在哪一区（与收藏跟踪行内共用同一张卡） */}
      {current && (
        <ValuationApplyConfirm
          isOpen={applyOpen}
          onClose={() => { setApplyOpen(false); setApplyError(''); }}
          report={current}
          effectiveLevels={effectiveLevels}
          currentPrice={currentPrice}
          onApply={handleApply}
          applyPending={applyPending}
          applyError={applyError}
        />
      )}
    </div>
  );
}
