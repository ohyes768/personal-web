/**
 * 报告详情：markdown 渲染（react-markdown + remark-gfm + rehype-sanitize）
 * 安全硬性要求：报告内容为 LLM 生成的不可信输入，必须经 rehype-sanitize 白名单
 * （默认 schema + 允许 a 的 target/rel），禁止 dangerouslySetInnerHTML
 */
'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { ReportDetail } from '@/lib/types/reports';
import { REPORT_SOURCE_LABELS } from '@/lib/types/reports';
import { deleteReport } from '@/lib/hooks/reports';

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
  /** 删除成功后回调（父层清选中 + 刷新列表） */
  onDeleted: () => void;
}

/** url 只放行 http(s)（与 rehype-sanitize 协议白名单一致），杜绝 javascript: 等伪协议注入 */
function safeHref(url: string): string | null {
  return /^https?:\/\//i.test(url) ? url : null;
}

export function ReportViewer({ detail, isLoading, error, onBack, onDeleted }: ReportViewerProps) {
  const reportHref = detail ? safeHref(detail.url) : null;
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleDelete = async () => {
    if (!detail) return;
    if (!window.confirm(`确定删除该报告？\n${detail.title}`)) return;

    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteReport(detail.report_id);
      onDeleted();
    } catch (err) {
      const message = err instanceof Error ? err.message : '删除失败';
      setDeleteError(message);
    } finally {
      setDeleting(false);
    }
  };

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
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-2xl font-bold text-white mb-2">{detail.title}</h2>
              {/* 删除：管理操作，前端免 token（后端已放开鉴权） */}
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                title="删除该报告"
                className="shrink-0 inline-flex items-center gap-1.5 rounded-md border border-red-900/70 bg-red-950/40 px-2.5 py-1.5 text-xs font-medium text-red-400 transition-colors hover:border-red-700 hover:bg-red-900/50 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                </svg>
                {deleting ? '删除中' : '删除'}
              </button>
            </div>
            {deleteError && <p className="text-red-400 text-xs mb-2">{deleteError}</p>}
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
