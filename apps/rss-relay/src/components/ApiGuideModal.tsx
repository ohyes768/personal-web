'use client';
/**
 * ApiGuideModal — 展示 rss-relay 对接文档（精简版）
 *
 * 内容来源：backend/rss-relay/README.md + endpoints.py 真实契约
 */

import { useEffect, useState, useRef } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
}

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch (err) {
      console.error('复制失败:', err);
    }
  };
  return (
    <div className="relative group my-3">
      {language && (
        <div className="absolute top-2 left-3 font-ui text-[10px] uppercase tracking-wider text-ink-soft">
          {language}
        </div>
      )}
      <button
        onClick={handleCopy}
        className="absolute top-2 right-2 font-ui text-[11px] px-2 py-1 rounded-[4px] bg-paper hover:bg-rule text-ink-muted hover:text-ink transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
      >
        {copied ? '✓ 已复制' : '复制'}
      </button>
      <pre className="font-mono text-[12.5px] leading-relaxed bg-paper-deep border border-rule rounded-[6px] p-4 overflow-x-auto text-ink-strong">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export default function ApiGuideModal({ open, onClose }: Props) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [allCopied, setAllCopied] = useState(false);

  const handleCopyAll = async () => {
    const content = contentRef.current;
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content.textContent || '');
      setAllCopied(true);
      setTimeout(() => setAllCopied(false), 1800);
    } catch (err) {
      console.error('复制失败:', err);
    }
  };

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/45 backdrop-blur-md flex items-start justify-center p-3 sm:p-6 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-paper-card rounded-[12px] w-full max-w-[760px] my-2 shadow-[0_8px_32px_rgba(43,42,40,0.15)] flex flex-col max-h-[calc(100vh-2rem)]"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-6 sm:px-8 pt-5 pb-4 border-b border-rule flex items-start justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="font-serif-cn text-[20px] sm:text-[22px] font-bold text-ink-strong">
              对接文档
            </h2>
            <button
              onClick={handleCopyAll}
              className="font-ui text-[12px] px-2.5 py-1 rounded-[4px] bg-paper hover:bg-rule text-ink-muted hover:text-ink transition-colors"
              title="复制全部内容"
            >
              {allCopied ? '✓ 已复制全部' : '复制全部'}
            </button>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 w-8 h-8 flex items-center justify-center rounded-full hover:bg-paper-deep transition-colors text-ink-muted hover:text-ink"
            aria-label="关闭"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div ref={contentRef} className="flex-1 overflow-y-auto px-6 sm:px-8 py-5 sm:py-6 font-ui text-[14px] text-ink leading-relaxed space-y-7">
          {/* 接口契约 */}
          <section>
            <h3 className="font-serif-cn text-[17px] font-bold text-ink-strong mb-2">
              接口契约
            </h3>
            <table className="w-full text-[13px] border-collapse mb-3">
              <thead>
                <tr className="border-b border-rule">
                  <th className="text-left py-1.5 pr-3 font-semibold text-ink-strong">方法</th>
                  <th className="text-left py-1.5 pr-3 font-semibold text-ink-strong">路径</th>
                  <th className="text-left py-1.5 font-semibold text-ink-strong">用途</th>
                </tr>
              </thead>
              <tbody className="text-ink-muted">
                <tr className="border-b border-rule/60">
                  <td className="py-1.5 pr-3"><code className="px-1 py-0.5 bg-accent/[0.08] text-accent rounded font-mono text-[11.5px]">POST</code></td>
                  <td className="py-1.5 pr-3 font-mono text-[12px]">/api/post</td>
                  <td className="py-1.5">推送 markdown（无鉴权）</td>
                </tr>
                <tr>
                  <td className="py-1.5 pr-3"><code className="px-1 py-0.5 bg-accent/[0.08] text-accent rounded font-mono text-[11.5px]">GET</code></td>
                  <td className="py-1.5 pr-3 font-mono text-[12px]">/api/rss.xml?token=xxx</td>
                  <td className="py-1.5">RSS 2.0 feed（token 必填）</td>
                </tr>
              </tbody>
            </table>
            <p className="text-[13px] mb-1">POST 请求体：</p>
            <ul className="list-disc list-inside text-[13px] text-ink-muted space-y-0.5 mb-3">
              <li><code className="font-mono text-[12px]">title</code> — <span className="text-danger font-semibold">必填</span>，文章标题</li>
              <li><code className="font-mono text-[12px]">content</code> — <span className="text-danger font-semibold">必填</span>，markdown 正文</li>
              <li><code className="font-mono text-[12px]">url</code> — 可选，原文链接</li>
              <li><code className="font-mono text-[12px]">source</code> — 可选，来源标识（推荐填，会成为 RSS 的 author + 前端分组标签）</li>
            </ul>
            <p className="text-[12.5px] text-ink-muted">
              提示：POST 无鉴权（依赖内网隔离）；保留 15 天；想改保留期就改 <code className="font-mono text-[11.5px] px-1 bg-paper-deep rounded">backend/rss-relay/config/app.yaml</code> 的 retention_days 后 rebuild。
            </p>
          </section>

          {/* curl */}
          <section>
            <h3 className="font-serif-cn text-[17px] font-bold text-ink-strong mb-2">
              curl
            </h3>
            <CodeBlock
              language="bash"
              code={`curl -X POST https://web.duomi77.cn:9443/api/rss-relay/post \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "OpenAI 发布 GPT-5",
    "content": "# GPT-5\\n\\n正文 markdown",
    "url": "https://openai.com/blog/gpt-5",
    "source": "openclaw"
  }'`}
            />
          </section>

          {/* Python */}
          <section>
            <h3 className="font-serif-cn text-[17px] font-bold text-ink-strong mb-2">
              Python
            </h3>
            <CodeBlock
              language="python"
              code={`import httpx

def push(title: str, content: str, url: str = "", source: str = "my-bot"):
    r = httpx.post(
        "https://web.duomi77.cn:9443/api/rss-relay/post",
        json={"title": title, "content": content, "url": url, "source": source},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()`}
            />
          </section>

          {/* RSS 阅读器订阅 */}
          <section>
            <h3 className="font-serif-cn text-[17px] font-bold text-ink-strong mb-2">
              RSS 阅读器订阅
            </h3>
            <CodeBlock
              language="text"
              code={`https://web.duomi77.cn:9443/rss/api/rss-relay/rss.xml?token=<RSS_RELAY_TOKEN>`}
            />
            <p className="text-[12.5px] text-ink-muted">
              <code className="font-mono text-[11.5px] px-1 bg-paper-deep rounded">RSS_RELAY_TOKEN</code> 在主仓库根目录的 <code className="font-mono text-[11.5px] px-1 bg-paper-deep rounded">.env</code> 里。
              新部署用 <code className="font-mono text-[11.5px] px-1 bg-paper-deep rounded">openssl rand -hex 32</code> 生成。
            </p>
          </section>
        </div>

        <footer className="px-6 sm:px-8 py-3 border-t border-rule flex justify-end shrink-0">
          <button
            onClick={onClose}
            className="font-ui text-[14px] px-4 py-2 rounded-[6px] bg-paper-deep hover:bg-rule text-ink-muted hover:text-ink transition-colors"
          >
            关闭
          </button>
        </footer>
      </div>
    </div>
  );
}