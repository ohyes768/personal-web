"use client";

/** 通用小部件：状态徽章、提示条、加载指示。 */

import { useEffect, useRef } from "react";
import type { Tone } from "@/lib/status";

export function StateBadge({ tone, title }: { tone: Tone; title?: string }) {
  return (
    <span className={`badge ${tone.tone}`} title={title}>
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

/** 操作反馈条：成功/信息类 4 秒自动消失，失败类常驻到手动点掉。 */
export function Toast({
  message,
  kind = "ok",
  onDismiss,
}: {
  message: string | null;
  kind?: "ok" | "error";
  onDismiss: () => void;
}) {
  const dismissRef = useRef(onDismiss);
  dismissRef.current = onDismiss;

  useEffect(() => {
    if (!message || kind === "error") return;
    const timer = setTimeout(() => dismissRef.current(), 4000);
    return () => clearTimeout(timer);
  }, [message, kind]);

  if (!message) return null;
  return (
    <div
      className={`copy-toast${kind === "error" ? " error" : ""}`}
      role={kind === "error" ? "alert" : "status"}
      onClick={() => dismissRef.current()}
    >
      {message}
    </div>
  );
}

/** 加载指示：按钮内联的旋转环。语义交给按钮本身（aria-busy + 文案），这里只画形状。 */
export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}
