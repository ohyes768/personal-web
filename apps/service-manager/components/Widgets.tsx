"use client";

/** 通用小部件：状态徽章、复制按钮、返回入口。 */

import { useState } from "react";
import type { Tone } from "@/lib/status";

export function StateBadge({ tone, title }: { tone: Tone; title?: string }) {
  return (
    <span className={`badge ${tone.tone}`} title={title ?? tone.label}>
      {tone.label}
    </span>
  );
}

export function CopyButton({
  value,
  label = "复制",
  onCopied,
}: {
  value: string;
  label?: string;
  onCopied?: (message: string) => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      onCopied?.("已复制");
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      onCopied?.("复制失败：浏览器拒绝访问剪贴板");
    }
  }

  return (
    <button type="button" className="btn btn-mini" onClick={copy}>
      {copied ? "已复制" : label}
    </button>
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

/** 只在 http/https 时渲染可点链接：用户录入的 URL 一律限协议。 */
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
