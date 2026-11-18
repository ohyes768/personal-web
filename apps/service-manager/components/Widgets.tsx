"use client";

/** 通用小部件：状态徽章、提示条、加载指示。 */

import type { Tone } from "@/lib/status";

export function StateBadge({ tone, title }: { tone: Tone; title?: string }) {
  return (
    <span className={`badge ${tone.tone}`} title={title ?? tone.label}>
      {tone.label}
    </span>
  );
}

/** 只在 http/https 时渲染成可点链接，其余退化成纯文本。 */
export function SafeLink({
  href,
  children,
  ...rest
}: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) {
  const allowed = /^https?:\/\//i.test(href);
  if (!allowed) {
    return <span className="mono wrap-anywhere">{href}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" {...rest}>
      {children}
    </a>
  );
}

export function Toast({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="copy-toast" role="status">
      {message}
    </div>
  );
}

/** 加载指示：按钮内联的旋转环。语义交给按钮本身（aria-busy + 文案），这里只画形状。 */
export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
