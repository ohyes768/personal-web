/**
 * 前端分段合并工具
 *
 * 与后端 backend/douyin-processor/src/server/segment_html.py::merge_segments_to_paragraphs
 * 保持同步：启发式合并规则（间隔 >1.5s 或 ≥120 字切段）。
 *
 * 保持两处实现同步的策略：测试或维护时同时改两处（前端 TS / 后端 Python）。
 * 当前刻意重复，避免引入 monorepo 跨语言共享机制。
 */

import type { TranscriptSegment } from './types';

export interface TranscriptParagraph {
  /** 段内起始时间（第一个 segment 的 start_time） */
  start_time: number;
  /** 段内 segments */
  segments: TranscriptSegment[];
}

/**
 * 把 ASR segments 启发式合并为"段"。
 *
 * 切段规则（按顺序判断）：
 * 1. 第一个 segment 开新段
 * 2. 后续 segment 若满足任一条件则切新段：
 *    - 跟前一段最后一个 segment 的 end_time 间隔 > gap_threshold
 *    - 当前段已累积 char 数 ≥ max_chars
 *
 * @param segments 阿里云 ASR 返回的段列表
 * @param gap_threshold 时间间隔阈值（秒），默认 1.5
 * @param max_chars 段内累积 char 数上限，默认 120
 */
export function mergeSegmentsToParagraphs(
  segments: TranscriptSegment[],
  gapThreshold: number = 1.5,
  maxChars: number = 120,
): TranscriptParagraph[] {
  if (!segments || segments.length === 0) {
    return [];
  }

  const paragraphs: TranscriptParagraph[] = [{ start_time: segments[0].start_time, segments: [segments[0]] }];

  for (const seg of segments.slice(1)) {
    const current = paragraphs[paragraphs.length - 1];
    const lastSeg = current.segments[current.segments.length - 1];

    // 间隔判断：缺 start_time/end_time 视为连续
    const gap = (seg.start_time != null && lastSeg.end_time != null)
      ? seg.start_time - lastSeg.end_time
      : 0;

    // 累积字符数（缺 text 视为空串）
    const currentChars = current.segments.reduce(
      (sum, s) => sum + (s.text?.length || 0),
      0,
    );

    if (gap > gapThreshold || currentChars >= maxChars) {
      paragraphs.push({ start_time: seg.start_time, segments: [seg] });
    } else {
      current.segments.push(seg);
    }
  }

  return paragraphs;
}
