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
