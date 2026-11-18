/**
 * 夏普走势弹框（列表代码 / 详情抽屉夏普卡片点击后弹出）
 *
 * 与「夏普走势」独立 tab 页共用 SharpeTrendBody —— 同一套 KPI 卡、同一张图、
 * 同一批空态文案，两边样式一致。
 *
 * 行为：
 * - 遮罩点击 / Escape / 右上角 × 关闭；打开时锁 body 滚动，关闭后焦点回到触发元素
 * - 区间切换（全部 / 近 3 年 / 近 1 年）在弹框内切，走 query 参数口径的同一个接口
 * - 头部保留「独立页」入口：想手动输代码 / 分享链接时去独立 tab 页
 */
'use client';

import { XMarkIcon } from '@heroicons/react/24/outline';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import {
  DEFAULT_TREND_RANGE,
  sharpeTrendHref,
  type SharpeTrendRange,
} from '@/lib/sharpe-trend';
import { useSharpeTrend } from '@/lib/useSharpeTrend';

import { SharpeTrendBody } from './SharpeTrendBody';

export interface SharpeTrendDialogProps {
  /** 基金代码；null = 不渲染弹框 */
  code: string | null;
  onClose: () => void;
}

export function SharpeTrendDialog({ code, onClose }: SharpeTrendDialogProps) {
  const [range, setRange] = useState<SharpeTrendRange>(DEFAULT_TREND_RANGE);
  const { data, loading, error, reload } = useSharpeTrend(code, range);

  // onClose 每次渲染都可能是新函数，用 ref 兜住，避免 Escape 监听反复重挂
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const closeRef = useRef<HTMLButtonElement>(null);

  // 换一只基金 → 区间回到默认（否则会带着上一只的筛选看新基金）
  useEffect(() => {
    setRange(DEFAULT_TREND_RANGE);
  }, [code]);

  // Escape 关闭 + body 滚动锁定 + 焦点回到触发元素
  useEffect(() => {
    if (!code) return;
    // 捕获阶段拦截：本弹框常开在「详情抽屉」之上（抽屉也监听 document 的 Escape）。
    // 若在冒泡阶段处理，两个监听都会触发 → 两层一起关，且两处 body.overflow 恢复互相打架。
    // capture + stopPropagation 让 Escape 只关最上层弹框，事件不再传到抽屉的 bubble 监听。
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      onCloseRef.current();
    };
    document.addEventListener('keydown', handleKeyDown, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, [code]);

  if (!code) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-start sm:items-center justify-center p-3 sm:p-6">
      <div
        className="absolute inset-0 bg-black/50 transition-opacity duration-200"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="sharpe-trend-dialog-title"
        className="relative w-full max-w-4xl max-h-[92vh] bg-paper-card border border-rule rounded-xl shadow-xl flex flex-col overflow-hidden"
      >
        {/* 头部：基金名 + 代码 + 口径 + 独立页入口 + 关闭 */}
        <div className="flex items-start justify-between gap-3 px-4 sm:px-5 py-3 border-b border-rule bg-paper-tint">
          <div className="min-w-0">
            <div className="flex items-baseline gap-2 min-w-0">
              <h2
                id="sharpe-trend-dialog-title"
                className="text-base font-semibold text-ink-strong truncate"
                style={{ fontFamily: 'var(--font-serif)' }}
              >
                {data?.name ?? code}
              </h2>
              <span className="font-mono text-xs text-info shrink-0">{code}</span>
            </div>
            <p className="mt-0.5 text-[11px] text-ink-muted">
              夏普走势 · 现算滚动 3 年 · 与夏普榜单同口径
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Link
              href={sharpeTrendHref(code, range)}
              onClick={onClose}
              className="px-2 py-1 rounded-md text-[11px] text-info hover:bg-info-tint transition-colors"
              title="在独立「夏普走势」页打开（可手动输入代码）"
            >
              独立页
            </Link>
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              className="min-h-9 min-w-9 flex items-center justify-center text-ink-muted hover:text-ink-strong hover:bg-paper-deep rounded transition-colors"
              aria-label="关闭夏普走势"
            >
              <XMarkIcon className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* 内容：区间切换 + KPI + 曲线 */}
        <div className="flex-1 overflow-y-auto px-3 sm:px-4 py-3">
          <SharpeTrendBody
            data={data}
            loading={loading}
            error={error}
            onRetry={reload}
            range={range}
            onRangeChange={setRange}
          />
        </div>
      </div>
    </div>
  );
}
