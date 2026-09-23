/**
 * 报告详情：markdown 渲染（react-markdown + remark-gfm + rehype-sanitize）
 * 安全硬性要求：报告内容为 LLM 生成的不可信输入，必须经 rehype-sanitize 白名单
 * （默认 schema + 允许 a 的 target/rel），禁止 dangerouslySetInnerHTML
 */
'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { ReportDetail } from '@/lib/types/reports';
import { REPORT_SOURCE_LABELS } from '@/lib/types/reports';

/** 默认白名单基础上放行 a 链接的 target / rel（外链新窗口打开） */
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), 'target', 'rel'],
  },
};

interface ReportViewerProps {
  detail: ReportDetail | null;
  isLoading: boolean;
  error: string | null;
  onBack: () => void;
}

/** url 只放行 http(s)（与 rehype-sanitize 协议白名单一致），杜绝 javascript: 等伪协议注入 */
function safeHref(url: string): string | null {
  return /^https?:\/\//i.test(url) ? url : null;
}

export function ReportViewer({ detail, isLoading, error, onBack }: ReportViewerProps) {
  const reportHref = detail ? safeHref(detail.url) : null;
  return (
    <div className="h-full flex flex-col">
      {/* 移动端返回列表（lg 以上隐藏，两栏常驻无需返回） */}
      <button
        type="button"
        onClick={onBack}
        className="lg:hidden text-sm text-gray-400 hover:text-white transition-colors mb-4"
      >
        ← 返回列表
      </button>

      {isLoading ? (
        <div className="text-center text-gray-400 py-12">加载报告...</div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      ) : !detail ? (
        <div className="h-full flex items-center justify-center text-gray-500 py-24">
          从左侧选择一篇报告查看详情
        </div>
      ) : (
        <article className="min-w-0">
          {/* 报告元信息头 */}
          <header className="mb-6 pb-4 border-b border-gray-800">
            <h2 className="text-2xl font-bold text-white mb-2">{detail.title}</h2>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
              <span className="px-2 py-0.5 rounded bg-gray-800 text-gray-300">
                {REPORT_SOURCE_LABELS[detail.source] ?? detail.source}
              </span>
              <span>分析日期 {detail.analyzed_at.slice(0, 10)}</span>
              <span>推送时间 {detail.pushed_at.slice(0, 19).replace('T', ' ')}</span>
              {reportHref && (
                <a
                  href={reportHref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 transition-colors"
                >
                  原文链接
                </a>
              )}
            </div>
          </header>

          {/* markdown 正文：sanitize 在 rehype 管道内完成 */}
          <div className="prose prose-invert max-w-none prose-heads:text-white prose-a:text-blue-400 break-words">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
            >
              {detail.content}
            </ReactMarkdown>
          </div>
        </article>
      )}
    </div>
  );
}
