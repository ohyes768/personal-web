/**
 * 估值资料阅读入口（主页面 / 收藏跟踪行 → 独立阅读页）
 *
 * 用普通同源 <a> 做完整导航（不做 Next 客户端路由）：
 * 线上部署时应用 basePath 为空、nginx 剥掉 /dividend 前缀，
 * 客户端路由会按带前缀路径取缓存导致不一致，完整导航最稳。
 *
 * 服务端/水合前使用同目录相对 href ./valuation-reader（本地与线上都能解析到正确地址），
 * 挂载后再按浏览器真实 pathname 计算绝对地址并带上返回视图参数。
 *
 * 三种外观（不用传任意 className，避免和 .quality-reader-entry 的固定盒型打架）：
 * - default：页面入口大按钮（44px 触控高度，手机上友好）
 * - toolbar：工具栏里的紧凑按钮，与队列按钮、搜索框同高（38px）
 * - inline：行内文字链接（表格行里用）
 */
'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { readerHref, reportHref } from '@/lib/valuation-reader';

/** 工具栏紧凑按钮：与相邻的队列按钮（px-3 py-2 text-sm）和搜索框同一盒型 */
const TOOLBAR_CLASS =
  'inline-flex items-center rounded border border-rule-strong bg-paper-card px-3 py-2 text-sm text-accent no-underline transition-colors hover:border-accent';

/** 行内文字链接：表格行里跟在状态徽章旁边 */
const INLINE_CLASS = 'text-xs text-accent hover:underline underline-offset-4';

export interface ValuationReaderEntryProps {
  /** 主页面当前 query（tab / fav 等），用于回跳时还原视图 */
  sourceQuery: string;
  /** 指定股票代码：行内「查看报告」用它直接落到那一份报告；不给则是阅读页入口 */
  code?: string;
  /** 外观 */
  variant?: 'default' | 'toolbar' | 'inline';
  /** 链接文字 */
  children?: ReactNode;
  /** 无障碍标签 */
  ariaLabel?: string;
}

export function ValuationReaderEntry({
  sourceQuery,
  code,
  variant = 'default',
  children,
  ariaLabel,
}: ValuationReaderEntryProps) {
  const [href, setHref] = useState('./valuation-reader');

  useEffect(() => {
    const query = new URLSearchParams(sourceQuery);
    setHref(code
      ? reportHref(window.location.pathname, code, query)
      : readerHref(window.location.pathname, query));
  }, [code, sourceQuery]);

  const className = variant === 'toolbar' ? TOOLBAR_CLASS
    : variant === 'inline' ? INLINE_CLASS
      : 'quality-reader-entry';

  return (
    <a
      href={href}
      className={className}
      data-testid={code ? 'valuation-report-link' : 'valuation-reader-entry'}
      aria-label={ariaLabel}
    >
      {children ?? '估值资料阅读'}
    </a>
  );
}
