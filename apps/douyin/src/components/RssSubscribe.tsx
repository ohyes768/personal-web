'use client';

/**
 * RssSubscribe 组件
 * 抖音模块的 RSS 订阅入口 — header 按钮 + 弹框（显示订阅 URL + 复制 + 已复制反馈）
 *
 * URL 是全站唯一的：用户把这个 URL 添加到 FreshRSS / Feedly / Inoreader 等 RSS reader。
 * 鉴权 token 来自 NEXT_PUBLIC_DOUYIN_RSS_TOKEN 环境变量（build 时内联）。
 */

import { useState } from 'react';

const RSS_URL_BASE = 'https://web.duomi77.cn:9443/api/douyin/rss.xml';

export function RssSubscribe() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const token = process.env.NEXT_PUBLIC_DOUYIN_RSS_TOKEN || '';
  const url = `${RSS_URL_BASE}?token=${token}`;
  const disabled = !token;

  const handleCopy = async () => {
    if (disabled) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('复制失败:', err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') setOpen(false);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={disabled}
        className="font-ui px-3.5 py-2 rounded-md text-[13px] cursor-pointer transition-all inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed border border-rule text-ink bg-paper hover:border-ink-soft"
        title={disabled ? '未配置 NEXT_PUBLIC_DOUYIN_RSS_TOKEN' : '查看 RSS 订阅源 URL'}
      >
        <svg
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M6 5c7.18 0 13 5.82 13 13M6 11a7 7 0 017 7m-6 0a1 1 0 11-2 0 1 1 0 012 0z"
          />
        </svg>
        RSS
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-md p-4 sm:p-6 flex items-start sm:items-center justify-center"
          onClick={() => setOpen(false)}
          onKeyDown={handleKeyDown}
        >
          <div
            className="bg-paper rounded-lg shadow-2xl w-full max-w-[560px] p-6 sm:p-8"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-serif-cn font-bold text-[20px] text-ink-strong mb-2 tracking-wide">
              RSS 订阅源
            </h2>
            <p className="font-ui text-[13px] text-ink-muted mb-5 leading-relaxed">
              把这个 URL 添加到 FreshRSS / Feedly / Inoreader 等 RSS 阅读器即可订阅。
              订阅源会自动拉取所有已转写完成的视频文字稿。
            </p>

            <div className="flex items-stretch gap-2 mb-3">
              <input
                readOnly
                value={url}
                onClick={(e) => e.currentTarget.select()}
                className="font-mono text-[12px] flex-1 px-3 py-2 border border-rule rounded-md bg-paper-deep text-ink focus:outline-none focus:border-accent"
              />
              <button
                onClick={handleCopy}
                disabled={disabled}
                className="font-ui px-4 py-2 text-[13px] rounded-md border border-accent text-accent bg-accent/[0.04] hover:bg-accent hover:text-paper transition-all disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {copied ? '✓ 已复制' : '复制'}
              </button>
            </div>

            <p className="font-ui text-[12px] text-ink-muted leading-relaxed">
              ⚠️ URL 含鉴权 token，请勿公开分享给他人
            </p>

            <div className="mt-6 flex justify-end">
              <button
                onClick={() => setOpen(false)}
                className="font-ui px-4 py-2 text-[13px] rounded-md border border-rule text-ink bg-paper hover:border-ink-soft transition-all"
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
