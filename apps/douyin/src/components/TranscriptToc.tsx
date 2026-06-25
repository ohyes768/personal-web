"use client";

import { useEffect, useState } from "react";
import type { TranscriptSegment } from "@/lib/types";

export interface TranscriptTocProps {
  segments: TranscriptSegment[];
}

/**
 * 文字稿目录组件
 * - 右侧浮窗，显示每个 segment 的前 20 字
 * - scroll spy 高亮当前可见段
 * - 点击平滑滚动到对应段
 */
export function TranscriptToc({ segments }: TranscriptTocProps) {
  const [activeIdx, setActiveIdx] = useState(0);

  // scroll spy：监听每个 segment 是否进入可视区
  useEffect(() => {
    if (segments.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const idx = Number(entry.target.getAttribute("data-seg-idx"));
            if (!Number.isNaN(idx)) setActiveIdx(idx);
          }
        });
      },
      { rootMargin: "-30% 0px -60% 0px", threshold: 0 },
    );

    document
      .querySelectorAll<HTMLElement>("[data-seg-idx]")
      .forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [segments]);

  // 让激活的 TOC 项滚到可视区
  useEffect(() => {
    const activeEl = document.querySelector(`[data-toc-idx="${activeIdx}"]`);
    activeEl?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIdx]);

  const handleClick = (idx: number) => {
    const target = document.querySelector<HTMLElement>(
      `[data-seg-idx="${idx}"]`,
    );
    target?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <aside className="hidden lg:block sticky top-0 self-start max-h-screen overflow-y-auto bg-paper-deep border-l border-rule p-12 lg:p-14">
      <div className="font-ui text-[11px] uppercase tracking-[0.2em] text-ink-soft font-semibold mb-5 flex items-center gap-2">
        <span>目录</span>
        <span className="flex-1 h-px bg-rule" />
      </div>
      <ul className="list-none p-0 m-0">
        {segments.map((seg, idx) => (
          <li
            key={idx}
            data-toc-idx={idx}
            onClick={() => handleClick(idx)}
            className={`px-3 py-2.5 mb-1 rounded-md cursor-pointer text-[13px] leading-snug border-l-2 border-transparent transition-all ${
              idx === activeIdx
                ? "text-accent border-l-accent bg-accent/10 font-medium"
                : "text-ink-muted hover:bg-accent/5 hover:text-ink"
            }`}
          >
            <span className="tnum font-serif-en text-[11px] text-ink-soft block mb-0.5 tracking-wide">
              {formatTocTime(seg.start_time)}
            </span>
            {seg.text.slice(0, 22)}
            {seg.text.length > 22 ? "..." : ""}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function formatTocTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}