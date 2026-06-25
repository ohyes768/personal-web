# Douyin RSS 语义分段 实施计划（精简版）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把抖音视频转写从 RSS 里"平铺一段"升级为"带起始时间戳的语义段"，启发式合并规则：间隔 >1.5s 或 ≥120 字切段。

**Architecture:** 后端 `douyin-processor` 子模块新增 `segment_html.py` 工具模块（合并 + 渲染），改 `endpoints.py` RSS 端点的 `content_encoded` 拼装链（segments → 合并 → HTML，fallback 到 `\n\n` 切 / 整段 `<p>`）。**无单元测试**，靠 1 次端到端 curl 验证。

**Tech Stack:** Python 3.12、FastAPI、uv（开发时用 `.venv`）、现有 `rss_utils.xml_escape/cdata_safe` 工具。

**Spec:** `docs/superpowers/specs/2026-06-25-douyin-rss-segmentation-design.md`

**工作目录**：所有路径相对 `backend/douyin-processor/`（子模块根），除非另注。

---

## 文件结构

| 文件 | 状态 | 责任 |
|------|------|------|
| `backend/douyin-processor/src/server/segment_html.py` | 新增 | 合并算法 + HTML 渲染 + 时间戳格式化 |
| `backend/douyin-processor/src/server/endpoints.py` | 修改 | RSS 端点 `_read_output_doc` + fallback 链 |
| `backend/douyin-processor/src/server/rss_utils.py` | 修改 | 仅 docstring 补充一句说明 |

---

## 任务 1: 新增 `segment_html.py`

**Files:**
- Create: `backend/douyin-processor/src/server/segment_html.py`

- [ ] **Step 1: 写文件**

`backend/douyin-processor/src/server/segment_html.py`：
```python
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


def format_ts(seconds: float) -> str:
    """秒数 → 'MM:SS' 或 'H:MM:SS' 格式。

    0.28 → "00:00"
    75.4 → "01:15"
    3725 → "1:02:05"
    3600 → "1:00:00"
    """
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def render_paragraphs_html(paragraphs: list[list[dict]]) -> str:
    """段 → HTML 字符串。

    每段渲染为:
        <p><span class="ts">MM:SS</span> 段内文本</p>

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
        ts = format_ts(paragraph[0].get("start_time", 0))
        text = " ".join((seg.get("text", "") or "") for seg in paragraph)
        parts.append(f'<p><span class="ts">{ts}</span> {xml_escape(text)}</p>')

    return "\n".join(parts)
```

- [ ] **Step 2: import 验证**

```bash
cd backend/douyin-processor
.venv/bin/python -c "from src.server.segment_html import merge_segments_to_paragraphs, format_ts, render_paragraphs_html; print('OK')"
```

Expected: `OK`，无 ImportError 或 SyntaxError。

- [ ] **Step 3: 快速手算 sanity check**

```bash
cd backend/douyin-processor
.venv/bin/python -c "
from src.server.segment_html import merge_segments_to_paragraphs, format_ts, render_paragraphs_html
segs = [
    {'start_time': 0.0, 'end_time': 1.0, 'text': '第一段', 'confidence': 1.0},
    {'start_time': 3.0, 'end_time': 4.0, 'text': '第二段', 'confidence': 1.0},
]
paragraphs = merge_segments_to_paragraphs(segs)
print('paragraphs:', len(paragraphs))
print('html:')
print(render_paragraphs_html(paragraphs))
print('format_ts(75.4):', format_ts(75.4))
"
```

Expected: 输出 2 段、HTML 含 `00:00` / `00:03`、`format_ts(75.4) = 01:15`

- [ ] **Step 4: Commit**

```bash
cd backend/douyin-processor
git add src/server/segment_html.py
git commit -m "feat(segment_html): add merge/format/render for RSS semantic segmentation"
```

---

## 任务 2: 改 `endpoints.py` RSS 端点

**Files:**
- Modify: `backend/douyin-processor/src/server/endpoints.py`

- [ ] **Step 1: 新增 `_read_output_doc` 函数**

在 `endpoints.py:872`（`_read_output_text` 函数定义结束）**之后**追加：
```python


async def _read_output_doc(aweme_id: str) -> Optional[dict]:
    """读 output/{aweme_id}.json，返回 {text, segments}。

    损坏/缺失 → None（单条跳过，不阻塞 RSS feed）。
    """
    try:
        result_file = Path(processor.output_dir) / f"{aweme_id}.json"
        if not result_file.exists():
            logger.warning(f"RSS: output 文件缺失 {aweme_id}")
            return None
        data = load_json(str(result_file))
        if not data:
            return None
        return {
            "text": data.get("text", "") or "",
            "segments": data.get("segments") or None,
        }
    except Exception as e:
        logger.warning(f"RSS: 读 output 失败 {aweme_id}: {e}")
        return None
```

> 旧的 `_read_output_text` **保留**（可能其他端点用），我们仅在 RSS 端点改用新函数。

- [ ] **Step 2: 替换 RSS 端点的并发读取和拼装逻辑**

替换 `endpoints.py:940-969` 区域（原 940 行 `texts = await asyncio.gather(...)` 到 969 行的 `items.append({...})`）：

**OLD**：
```python
        # 5. 并发读 output text
        texts = await asyncio.gather(
            *[_read_output_text(aid) for aid, _ in candidates]
        )

        # 6. 拼装 item dict
        base_url = _RSS_CHANNEL_META.get("link", "").rstrip("/")
        items: list[dict] = []
        for (aweme_id, st), text in zip(candidates, texts):
            if text is None:
                continue  # output 损坏/缺失的跳过
            title = st.get("title") or f"视频 {aweme_id}"
            author = st.get("author") or "未知作者"
            description_field = st.get("description") or ""
            pub_dt = _parse_iso_datetime(
                st.get("processed_at")
                or st.get("pending_at")
                or st.get("created_at")
            ) or datetime.now()

            items.append({
                "title": title,
                "link": f"{base_url}/douyin/?video={aweme_id}",
                "description": truncate_for_summary(text, 200),
                "author": author,
                "categories": extract_hashtags(description_field, max_n=5),
                "pub_date": pub_dt,
                "guid": aweme_id,
                "content_encoded": text,
            })
```

**NEW**：
```python
        # 5. 并发读 output doc（text + segments）
        docs = await asyncio.gather(
            *[_read_output_doc(aid) for aid, _ in candidates]
        )

        # 6. 拼装 item dict
        from src.server.rss_utils import xml_escape
        from src.server.segment_html import merge_segments_to_paragraphs, render_paragraphs_html

        base_url = _RSS_CHANNEL_META.get("link", "").rstrip("/")
        items: list[dict] = []
        for (aweme_id, st), doc in zip(candidates, docs):
            if doc is None or not doc["text"]:
                continue  # output 损坏/缺失 → 跳过
            text = doc["text"]
            segments = doc["segments"]

            title = st.get("title") or f"视频 {aweme_id}"
            author = st.get("author") or "未知作者"
            description_field = st.get("description") or ""
            pub_dt = _parse_iso_datetime(
                st.get("processed_at")
                or st.get("pending_at")
                or st.get("created_at")
            ) or datetime.now()

            # 分段策略（按优先级）
            if segments:
                paragraphs = merge_segments_to_paragraphs(segments)
                body = render_paragraphs_html(paragraphs)
            elif "\n\n" in text:
                # 旧数据有预分段 → 按 \n\n 切
                body = "\n".join(
                    f"<p>{xml_escape(p.strip())}</p>"
                    for p in text.split("\n\n") if p.strip()
                )
            else:
                # 兜底：整段单 <p>
                body = f"<p>{xml_escape(text.strip())}</p>"

            items.append({
                "title": title,
                "link": f"{base_url}/douyin/?video={aweme_id}",
                "description": truncate_for_summary(text, 200),
                "author": author,
                "categories": extract_hashtags(description_field, max_n=5),
                "pub_date": pub_dt,
                "guid": aweme_id,
                "content_encoded": body,
            })
```

- [ ] **Step 3: 验证 import**

```bash
cd backend/douyin-processor
.venv/bin/python -c "from src.server.endpoints import rss_feed, _read_output_doc; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd backend/douyin-processor
git add src/server/endpoints.py
git commit -m "feat(rss): add semantic segmentation to content_encoded"
```

---

## 任务 3: 更新 `rss_utils.py` docstring

**Files:**
- Modify: `backend/douyin-processor/src/server/rss_utils.py:1-7`

- [ ] **Step 1: 顶部 docstring 追加说明**

把现有（1-7 行）：
```python
"""
RSS 2.0 订阅源工具函数
为 /api/rss.xml 端点提供 XML 转义、CDATA 安全、日期格式化、hashtag 提取、摘要截断和 RSS 文档拼装。

为什么手写不用 feedgen：项目零 XML 依赖，RSS 2.0 模板固定，手写 ~120 行足够可控。
"""
```

改为：
```python
"""
RSS 2.0 订阅源工具函数
为 /api/rss.xml 端点提供 XML 转义、CDATA 安全、日期格式化、hashtag 提取、摘要截断和 RSS 文档拼装。

content_encoded 字段已分段（见 endpoints.py）：优先用 segments 启发式合并为带时间戳的段，
旧数据 fallback 到 \\n\\n 切 / 整段 <p>。

为什么手写不用 feedgen：项目零 XML 依赖，RSS 2.0 模板固定，手写 ~120 行足够可控。
"""
```

- [ ] **Step 2: 验证 import**

```bash
cd backend/douyin-processor
.venv/bin/python -c "from src.server.rss_utils import build_rss_xml; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd backend/douyin-processor
git add src/server/rss_utils.py
git commit -m "docs(rss_utils): note content_encoded is now segmented"
```

---

## 任务 4: 端到端验证

**Files:**
- 不改文件，纯验证

- [ ] **Step 1: 启动 uvicorn**

```bash
cd backend/douyin-processor
.venv/bin/uvicorn src.server.main:app --host 127.0.0.1 --port 8093
```

后台跑（用 `&` 或新 terminal）。

- [ ] **Step 2: 拉取 RSS 验证**

```bash
TOKEN=$(grep DOUYIN_RSS_TOKEN backend/douyin-processor/.env | cut -d= -f2)
curl -sS "http://127.0.0.1:8093/api/rss.xml?token=$TOKEN&limit=2" -o /tmp/rss.xml
echo "--- size ---"
wc -c /tmp/rss.xml
echo "--- 第一个 item 的 content:encoded 前 800 字 ---"
python -c "
import re
data = open('/tmp/rss.xml', encoding='utf-8').read()
m = re.search(r'<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>', data, re.DOTALL)
if m:
    print(m.group(1)[:800])
else:
    print('NO content:encoded found')
"
```

Expected:
- 第一个 item 的 content 包含 `<p><span class="ts">00:0X</span> ...</p>` 形式
- 出现至少 1 个段（短视频可能 1 段、长视频 ≥ 2 段）

如果 401 错：检查 token 是否跟 `.env` 一致。

- [ ] **Step 3: 停 uvicorn**

```bash
# 找到进程并 kill
pkill -f "uvicorn src.server.main" || true
```

- [ ] **Step 4: Commit（如果验证通过但前面 commit 有遗漏）**

> 通常不需要新 commit。如果验证失败需要回滚，单独处理。

---

## 任务 5: 主仓库 gitlink bump + push

**Files:**
- 主仓库 `backend/douyin-processor` gitlink

- [ ] **Step 1: 子模块 push（顺序：先子模块，后主仓库）**

```bash
cd backend/douyin-processor
git push origin main
```

Expected: push 成功，远端 4 个新 commit（segment_html / endpoints / rss_utils / 可能有空 commit）。

- [ ] **Step 2: 主仓库 stage gitlink**

```bash
cd /f/github/person_project/personal-web
git add backend/douyin-processor
git status
```

Expected: `M backend/douyin-processor`（gitlink 变化）

- [ ] **Step 3: 主仓库 commit + push**

```bash
cd /f/github/person_project/personal-web
git commit -m "chore: bump douyin-processor pointer（RSS 语义分段）"
git push origin master
```

Expected: 主仓库 1 个新 commit，远端同步。

---

## 自检 Checklist

- [ ] 任务 1 segment_html.py 三个函数 + import 验证
- [ ] 任务 2 endpoints.py `_read_output_doc` + fallback 链
- [ ] 任务 3 rss_utils.py docstring
- [ ] 任务 4 curl 端到端验证看到 `<p><span class="ts">` 标签
- [ ] 任务 5 子模块 push → 主仓库 gitlink bump → 主仓库 push

总计: 5 任务 / 0 测试 / 1 次端到端验证。
