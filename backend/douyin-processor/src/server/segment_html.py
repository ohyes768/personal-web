"""语义分段 + HTML 渲染工具

把阿里云 ASR 返回的 segments 启发式合并为"段"，再渲染成 RSS 用的 HTML。
合并规则（按顺序判断）：
1. 第一个 segment 开新段
2. 后续 segment 若满足任一条件则切新段：
   - 跟前一段最后一个 segment 的 end_time 间隔 > gap_threshold
   - 当前段已累积 char 数 ≥ max_chars
"""


def merge_segments_to_paragraphs(
    segments: list[dict],
    gap_threshold: float = 1.5,
    max_chars: int = 120,
) -> list[list[dict]]:
    """把 ASR segments 分组成"段"。

    Args:
        segments: 阿里云 ASR 返回的段列表，每段含 start_time/end_time/text/confidence
        gap_threshold: 时间间隔阈值（秒），超过则切段
        max_chars: 段内累积 char 数上限，达到则切段

    Returns:
        段列表：[[seg, seg, ...], [seg, seg, ...], ...]
        segments 为空时返回 []
    """
    if not segments:
        return []

    paragraphs: list[list[dict]] = [[segments[0]]]

    for seg in segments[1:]:
        current = paragraphs[-1]
        last_seg = current[-1]

        # 间隔判断：缺 start_time/end_time 视为连续
        last_end = last_seg.get("end_time")
        curr_start = seg.get("start_time")
        gap = (curr_start - last_end) if (last_end is not None and curr_start is not None) else 0.0

        # 累积字符数（缺 text 视为空串）
        current_chars = sum(len(s.get("text", "") or "") for s in current)

        if gap > gap_threshold or current_chars >= max_chars:
            paragraphs.append([seg])
        else:
            current.append(seg)

    return paragraphs


def render_paragraphs_html(paragraphs: list[list[dict]]) -> str:
    """段 → HTML 字符串。

    每段渲染为:
        <p>段内文本</p>

    段内各 segment 的 text 用单个空格 " " 拼接。
    多段之间用换行符 \\n 分隔（不影响 XML 解析，RSS reader 折叠）。
    段内文本会做 XML 实体转义（< > & " '）。
    """
    from src.server.rss_utils import xml_escape

    if not paragraphs:
        return ""

    parts: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        text = " ".join((seg.get("text", "") or "") for seg in paragraph)
        parts.append(f'<p>{xml_escape(text)}</p>')

    return "\n".join(parts)
