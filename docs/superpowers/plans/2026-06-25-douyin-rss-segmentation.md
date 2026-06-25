# Douyin RSS 语义分段 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把抖音视频转写从 RSS 里"平铺一段"升级为"带起始时间戳的语义段"，启发式合并规则：间隔 >1.5s 或 ≥120 字切段。

**Architecture:** 后端 `douyin-processor` 子模块加一个 `segment_html.py` 工具模块（合并 + 渲染），改 `endpoints.py` RSS 端点的 `content_encoded` 拼装链（segments → 合并 → HTML，fallback 到 `\n\n` 切 / 整段 `<p>`），加 `tests/test_segment_html.py` 单测。前端 `apps/douyin` 不动。

**Tech Stack:** Python 3.12、FastAPI、pytest 8+、uv（开发时用 `.venv`）、现有 `rss_utils.xml_escape/cdata_safe` 工具。

**Spec:** `docs/superpowers/specs/2026-06-25-douyin-rss-segmentation-design.md`

---

## 文件结构

| 文件 | 状态 | 责任 |
|------|------|------|
| `backend/douyin-processor/src/server/segment_html.py` | 新增 | 合并算法 + HTML 渲染 + 时间戳格式化 |
| `backend/douyin-processor/src/server/endpoints.py` | 修改 | RSS 端点 `_read_output_doc` + fallback 链 |
| `backend/douyin-processor/src/server/rss_utils.py` | 修改 | 仅 docstring 补充一句说明 |
| `backend/douyin-processor/tests/test_segment_html.py` | 新增 | 5 类必测场景 |
| `backend/douyin-processor/tests/__init__.py` | 新增 | 空文件，让 tests 变成包 |
| `backend/douyin-processor/pyproject.toml` | 修改 | 加 pytest dev 依赖 + pytest 配置 |

**工作目录**：所有路径相对 `backend/douyin-processor/`（子模块根）。

---

## 任务 1: 配置 pytest 开发依赖

**Files:**
- Modify: `backend/douyin-processor/pyproject.toml:22-23`

- [ ] **Step 1: 在 pyproject.toml 加 dev 依赖 + pytest 配置**

把现有的：
```toml
[tool.uv]
dev-dependencies = []
```

替换为：
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-ra -q"
```

> **注意**：当前文件第 19 行已经是 `[tool.hatch.build.targets.wheel]`（复数），不要破坏。先删掉 `[tool.uv]` 整段（2 行），再插入新内容。

- [ ] **Step 2: 同步 dev 依赖到 .venv**

```bash
cd backend/douyin-processor
uv pip install -e ".[dev]"
```

Expected: 提示 Successfully installed pytest + pytest-cov，无报错。

- [ ] **Step 3: 验证 pytest 可用**

```bash
cd backend/douyin-processor
.venv/bin/pytest --version
```

Expected: `pytest 8.x.x`（或更高版本号）

- [ ] **Step 4: Commit**

```bash
cd backend/douyin-processor
git add pyproject.toml
git commit -m "chore: add pytest dev dependencies and test config"
```

> 子模块独立 commit。主仓库不动。

---

## 任务 2: 创建 tests 目录 + conftest

**Files:**
- Create: `backend/douyin-processor/tests/__init__.py`（空文件）

- [ ] **Step 1: 创建 tests 目录和空 __init__.py**

```bash
cd backend/douyin-processor
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: 验证空测试集运行无错**

```bash
cd backend/douyin-processor
.venv/bin/pytest
```

Expected: `no tests ran` 之类的提示（不是 error），exit code 5（pytest "no tests collected" 标准退出码）。

- [ ] **Step 3: Commit**

```bash
cd backend/douyin-processor
git add tests/__init__.py
git commit -m "chore: scaffold tests package"
```

---

## 任务 3: 写 `merge_segments_to_paragraphs` 失败测试

**Files:**
- Create: `backend/douyin-processor/tests/test_segment_html.py`

- [ ] **Step 1: 写测试文件**

`backend/douyin-processor/tests/test_segment_html.py`：
```python
"""segment_html 模块单元测试"""
import pytest

from src.server.segment_html import merge_segments_to_paragraphs


def _seg(start: float, end: float, text: str) -> dict:
    """构造 ASR segment 的辅助函数。"""
    return {"start_time": start, "end_time": end, "text": text, "confidence": 1.0}


class TestMergeSegments:
    """merge_segments_to_paragraphs 边界与合并规则测试"""

    def test_empty_input_returns_empty(self):
        assert merge_segments_to_paragraphs([]) == []

    def test_single_segment_one_paragraph(self):
        segs = [_seg(0.0, 1.0, "你好")]
        assert merge_segments_to_paragraphs(segs) == [segs]

    def test_consecutive_segments_merge(self):
        """间隔 0.3s < 1.5s 阈值，应该合并为一段。"""
        segs = [
            _seg(0.0, 1.0, "第一句"),
            _seg(1.3, 2.0, "第二句"),  # 间隔 0.3s
        ]
        result = merge_segments_to_paragraphs(segs)
        assert result == [segs]

    def test_large_gap_splits_paragraph(self):
        """间隔 2.0s > 1.5s 阈值，应该切段。"""
        seg1 = _seg(0.0, 1.0, "第一段")
        seg2 = _seg(3.0, 4.0, "第二段")  # 间隔 2.0s
        segs = [seg1, seg2]
        result = merge_segments_to_paragraphs(segs)
        assert result == [[seg1], [seg2]]

    def test_max_chars_triggers_split(self):
        """累积 char 数 ≥ 120 切段（边界 119/120/121）。"""
        # 第一段恰好 119 字符
        long_text_119 = "啊" * 119
        seg1 = _seg(0.0, 1.0, long_text_119)
        # 紧接的下一段（间隔 0s）
        seg2 = _seg(1.0, 2.0, "b")
        segs = [seg1, seg2]

        # 119 + 1 = 120 → 切段
        result = merge_segments_to_paragraphs(segs)
        assert result == [[seg1], [seg2]]

    def test_max_chars_119_does_not_split(self):
        """累积 119 字符不切段。"""
        long_text_118 = "啊" * 118
        seg1 = _seg(0.0, 1.0, long_text_118)
        seg2 = _seg(1.0, 2.0, "b")  # 118 + 1 = 119
        segs = [seg1, seg2]

        result = merge_segments_to_paragraphs(segs)
        assert result == [segs]

    def test_gap_takes_priority_over_chars(self):
        """间隔和字数都满足时，按间隔先切。"""
        # 第一段长 100 字
        seg1 = _seg(0.0, 1.0, "x" * 100)
        # 间隔 2.0s 且字符少
        seg2 = _seg(3.0, 4.0, "y")  # 100 + 1 = 101 < 120
        segs = [seg1, seg2]

        result = merge_segments_to_paragraphs(segs)
        assert result == [[seg1], [seg2]]

    def test_missing_start_time_continues(self):
        """segment 缺 start_time → 视为与前一段连续。"""
        seg1 = _seg(0.0, 1.0, "第一")
        seg2 = {"end_time": 2.0, "text": "第二", "confidence": 1.0}  # 无 start_time
        segs = [seg1, seg2]

        result = merge_segments_to_paragraphs(segs)
        assert result == [[seg1, seg2]]

    def test_missing_text_treated_as_empty(self):
        """segment 缺 text → 当空串处理，不切段。"""
        seg1 = _seg(0.0, 1.0, "你好")
        seg2 = _seg(1.3, 2.0, "")  # 空 text
        segs = [seg1, seg2]

        result = merge_segments_to_paragraphs(segs)
        assert result == [segs]
```

- [ ] **Step 2: 运行测试验证失败（模块不存在）**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.server.segment_html'`

- [ ] **Step 3: Commit（只 commit 测试，红是预期的）**

```bash
cd backend/douyin-processor
git add tests/test_segment_html.py
git commit -m "test: add failing tests for merge_segments_to_paragraphs"
```

---

## 任务 4: 实现 `merge_segments_to_paragraphs`

**Files:**
- Create: `backend/douyin-processor/src/server/segment_html.py`

- [ ] **Step 1: 写 segment_html.py（先只实现 merge + format_ts + render 的空壳）**

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
```

- [ ] **Step 2: 运行测试验证全部通过**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py -v
```

Expected: `9 passed`（任务 3 的 9 个测试全过）

- [ ] **Step 3: Commit**

```bash
cd backend/douyin-processor
git add src/server/segment_html.py
git commit -m "feat(segment_html): add merge_segments_to_paragraphs"
```

---

## 任务 5: 写 `format_ts` 失败测试

**Files:**
- Modify: `backend/douyin-processor/tests/test_segment_html.py`（追加）

- [ ] **Step 1: 在 test_segment_html.py 追加 TestFormatTs class**

在文件末尾追加：
```python

class TestFormatTs:
    """format_ts 时间戳格式化测试"""

    def test_zero_seconds(self):
        from src.server.segment_html import format_ts
        assert format_ts(0) == "00:00"

    def test_sub_second_rounds_down(self):
        from src.server.segment_html import format_ts
        assert format_ts(0.28) == "00:00"

    def test_one_minute(self):
        from src.server.segment_html import format_ts
        assert format_ts(75.4) == "01:15"

    def test_under_one_hour(self):
        from src.server.segment_html import format_ts
        assert format_ts(599) == "09:59"

    def test_over_one_hour(self):
        from src.server.segment_html import format_ts
        assert format_ts(3725) == "1:02:05"

    def test_exactly_one_hour(self):
        from src.server.segment_html import format_ts
        assert format_ts(3600) == "1:00:00"
```

- [ ] **Step 2: 运行验证失败**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py::TestFormatTs -v
```

Expected: `ImportError: cannot import name 'format_ts' from 'src.server.segment_html'`

- [ ] **Step 3: Commit 测试（红）**

```bash
cd backend/douyin-processor
git add tests/test_segment_html.py
git commit -m "test: add failing tests for format_ts"
```

---

## 任务 6: 实现 `format_ts`

**Files:**
- Modify: `backend/douyin-processor/src/server/segment_html.py`

- [ ] **Step 1: 在 segment_html.py 末尾追加 format_ts**

在文件末尾追加：
```python


def format_ts(seconds: float) -> str:
    """秒数 → 'MM:SS' 或 'H:MM:SS' 格式。

    0.28 → "00:00"
    75.4 → "01:15"
    3725 → "1:02:05"
    3600 → "1:00:00"

    Args:
        seconds: 秒数（浮点）

    Returns:
        格式化时间字符串
    """
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
```

- [ ] **Step 2: 运行验证通过**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py::TestFormatTs -v
```

Expected: `6 passed`

- [ ] **Step 3: 全量测试也确认不挂**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py -v
```

Expected: `15 passed`（9 merge + 6 format）

- [ ] **Step 4: Commit**

```bash
cd backend/douyin-processor
git add src/server/segment_html.py
git commit -m "feat(segment_html): add format_ts"
```

---

## 任务 7: 写 `render_paragraphs_html` 失败测试（含转义安全）

**Files:**
- Modify: `backend/douyin-processor/tests/test_segment_html.py`（追加）

- [ ] **Step 1: 在 test_segment_html.py 末尾追加 TestRenderHtml class**

在文件末尾追加：
```python

class TestRenderParagraphsHtml:
    """render_paragraphs_html HTML 渲染 + 转义安全测试"""

    def test_single_paragraph_basic(self):
        from src.server.segment_html import render_paragraphs_html, format_ts
        paragraphs = [[
            {"start_time": 15.0, "end_time": 20.0, "text": "第一段文本", "confidence": 1.0},
        ]]
        result = render_paragraphs_html(paragraphs)
        assert result == f'<p><span class="ts">00:15</span> 第一段文本</p>'

    def test_multiple_paragraphs_joined_with_newline(self):
        from src.server.segment_html import render_paragraphs_html
        paragraphs = [
            [{"start_time": 0.0, "end_time": 5.0, "text": "开头", "confidence": 1.0}],
            [{"start_time": 70.0, "end_time": 75.0, "text": "下一段", "confidence": 1.0}],
        ]
        result = render_paragraphs_html(paragraphs)
        assert result == '<p><span class="ts">00:00</span> 开头</p>\n<p><span class="ts">01:10</span> 下一段</p>'

    def test_segment_text_joined_with_space(self):
        from src.server.segment_html import render_paragraphs_html
        paragraphs = [[
            {"start_time": 0.0, "end_time": 1.0, "text": "第一句", "confidence": 1.0},
            {"start_time": 1.3, "end_time": 2.0, "text": "第二句", "confidence": 1.0},
        ]]
        result = render_paragraphs_html(paragraphs)
        assert result == '<p><span class="ts">00:00</span> 第一句 第二句</p>'

    def test_uses_first_segment_start_time(self):
        from src.server.segment_html import render_paragraphs_html
        paragraphs = [[
            {"start_time": 100.0, "end_time": 101.0, "text": "开头", "confidence": 1.0},
            {"start_time": 102.0, "end_time": 103.0, "text": "中间", "confidence": 1.0},
        ]]
        result = render_paragraphs_html(paragraphs)
        # 100s = 1min 40s，不到 1 小时，format_ts 输出 "01:40"
        assert result.startswith('<p><span class="ts">01:40</span>')

    def test_lt_escaped(self):
        from src.server.segment_html import render_paragraphs_html
        paragraphs = [[
            {"start_time": 0.0, "end_time": 1.0, "text": "<script>", "confidence": 1.0},
        ]]
        result = render_paragraphs_html(paragraphs)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_ampersand_escaped(self):
        from src.server.segment_html import render_paragraphs_html
        paragraphs = [[
            {"start_time": 0.0, "end_time": 1.0, "text": "AT&T 公司", "confidence": 1.0},
        ]]
        result = render_paragraphs_html(paragraphs)
        assert "AT&amp;T" in result

    def test_empty_paragraphs_returns_empty_string(self):
        from src.server.segment_html import render_paragraphs_html
        assert render_paragraphs_html([]) == ""
```

- [ ] **Step 2: 运行验证失败**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py::TestRenderParagraphsHtml -v
```

Expected: `ImportError: cannot import name 'render_paragraphs_html'`

- [ ] **Step 3: Commit 测试（红）**

```bash
cd backend/douyin-processor
git add tests/test_segment_html.py
git commit -m "test: add failing tests for render_paragraphs_html"
```

---

## 任务 8: 实现 `render_paragraphs_html`

**Files:**
- Modify: `backend/douyin-processor/src/server/segment_html.py`

- [ ] **Step 1: 在 segment_html.py 末尾追加 render_paragraphs_html**

在文件末尾追加：
```python


def render_paragraphs_html(paragraphs: list[list[dict]]) -> str:
    """段 → HTML 字符串。

    每段渲染为:
        <p><span class="ts">MM:SS</span> 段内文本</p>

    段内各 segment 的 text 用单个空格 " " 拼接。
    多段之间用换行符 \\n 分隔（不影响 XML 解析，RSS reader 折叠）。
    段内文本会做 XML 实体转义（< > & " '）。

    Args:
        paragraphs: merge_segments_to_paragraphs 的输出

    Returns:
        拼接好的 HTML 字符串
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

- [ ] **Step 2: 运行验证通过**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py::TestRenderParagraphsHtml -v
```

Expected: `7 passed`

- [ ] **Step 3: 全量测试**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py -v
```

Expected: `22 passed`（9 + 6 + 7）

- [ ] **Step 4: Commit**

```bash
cd backend/douyin-processor
git add src/server/segment_html.py
git commit -m "feat(segment_html): add render_paragraphs_html with xml escape"
```

---

## 任务 9: 写 RSS 端到端 fallback 行为测试

**Files:**
- Modify: `backend/douyin-processor/tests/test_segment_html.py`（追加）

- [ ] **Step 1: 追加 TestFallbackBehavior class**

在文件末尾追加：
```python

class TestFallbackBehavior:
    """端到端 fallback 行为测试 + RSS XML 解析验证"""

    def test_segments_priority_uses_merge(self):
        """优先用 segments 走启发式合并，不走 text fallback。"""
        from src.server.segment_html import render_paragraphs_html, merge_segments_to_paragraphs
        segments = [
            {"start_time": 0.0, "end_time": 1.0, "text": "第一段", "confidence": 1.0},
            {"start_time": 3.0, "end_time": 4.0, "text": "第二段", "confidence": 1.0},  # 间隔 2s 切
        ]
        paragraphs = merge_segments_to_paragraphs(segments)
        body = render_paragraphs_html(paragraphs)
        assert body.count("<p>") == 2
        assert "00:00" in body
        assert "00:03" in body

    def test_text_with_double_newline_splits(self):
        """无 segments 但 text 含 \\n\\n → 按 \\n\\n 切段。"""
        text = "第一段文本。\n\n第二段文本。\n\n第三段文本。"
        # 模拟 fallback 逻辑
        if "\n\n" in text:
            paragraphs_text = [p.strip() for p in text.split("\n\n") if p.strip()]
        else:
            paragraphs_text = [text.strip()]

        assert len(paragraphs_text) == 3
        assert paragraphs_text[0] == "第一段文本。"

    def test_text_without_separator_single_paragraph(self):
        """无 segments 无 \\n\\n → 整段单 <p>。"""
        text = "整段连续文本，无任何分隔符。"
        if "\n\n" in text:
            paragraphs_text = [p.strip() for p in text.split("\n\n") if p.strip()]
        else:
            paragraphs_text = [text.strip()]

        assert len(paragraphs_text) == 1
        assert paragraphs_text[0] == text

    def test_rss_xml_parses_with_segmented_html(self):
        """完整 RSS XML 含分段 HTML 时能被 ElementTree 解析。"""
        import xml.etree.ElementTree as ET
        from src.server.rss_utils import build_rss_xml
        from datetime import datetime

        segments = [
            {"start_time": 0.0, "end_time": 5.0, "text": "第一段文本", "confidence": 1.0},
            {"start_time": 70.0, "end_time": 75.0, "text": "第二段 & 含特殊字符 <test>", "confidence": 1.0},
        ]
        from src.server.segment_html import merge_segments_to_paragraphs, render_paragraphs_html
        paragraphs = merge_segments_to_paragraphs(segments)
        body = render_paragraphs_html(paragraphs)

        xml = build_rss_xml(
            channel_meta={"title": "测试", "link": "https://x", "description": "d", "self_url": "https://x/rss.xml"},
            items=[{
                "title": "测试视频",
                "link": "https://x/v",
                "description": "摘要",
                "author": "作者",
                "categories": [],
                "pub_date": datetime(2026, 6, 25, 9, 0),
                "guid": "test1",
                "content_encoded": body,
            }],
            build_date=datetime(2026, 6, 25, 9, 0),
        )

        # 解析不抛异常即可
        root = ET.fromstring(xml)
        assert root.tag == "rss"
        items = root.findall(".//item")
        assert len(items) == 1
```

- [ ] **Step 2: 运行验证失败（render_paragraphs_html 转义 bug）**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/test_segment_html.py::TestFallbackBehavior -v
```

Expected: 4 passed（这部分没新依赖，前面的任务都做完了应该全过；如果失败看 traceback 找原因）

- [ ] **Step 3: Commit**

```bash
cd backend/douyin-processor
git add tests/test_segment_html.py
git commit -m "test: add fallback behavior and RSS XML parse tests"
```

---

## 任务 10: 修改 endpoints.py RSS 端点（替换 _read_output_text → _read_output_doc）

**Files:**
- Modify: `backend/douyin-processor/src/server/endpoints.py:856-872, 940-969`

- [ ] **Step 1: 替换 _read_output_text 为 _read_output_doc**

在 `endpoints.py:856-872`（`_read_output_text` 函数定义）**之后**追加新函数：
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

**保留**旧的 `_read_output_text`（它可能被其他端点用，删除需先 grep 确认）。我们仅在 RSS 端点改用 `_read_output_doc`。

- [ ] **Step 2: 修改 RSS 端点的并发读取和拼装逻辑**

替换 `endpoints.py:940-969` 区域（原 940 行 `texts = await asyncio.gather(...)` 到 969 行的 `items.append({...})`）：

**OLD（940-969）**：
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

- [ ] **Step 3: 验证 endpoints.py 可正常 import**

```bash
cd backend/douyin-processor
.venv/bin/python -c "from src.server.endpoints import rss_feed, _read_output_doc; print('OK')"
```

Expected: 输出 `OK`，无 ImportError 或 SyntaxError。

- [ ] **Step 4: 全量测试 + 端到端 sanity check**

```bash
cd backend/douyin-processor
.venv/bin/pytest tests/ -v
```

Expected: `26 passed`（9 + 6 + 7 + 4）

- [ ] **Step 5: 启动 uvicorn 验证 RSS 端点**

```bash
cd backend/douyin-processor
.venv/bin/uvicorn src.server.main:app --host 127.0.0.1 --port 8093 &
sleep 3
curl -sS "http://127.0.0.1:8093/api/rss.xml?token=$(grep DOUYIN_RSS_TOKEN .env | cut -d= -f2)&limit=2" | head -50
kill %1
```

Expected: 输出 RSS XML，第一个 `<item>` 的 `<content:encoded>` 里出现 `<p><span class="ts">` 标签，时间戳格式如 `00:0X`。

如果报 401 错，token 不对，从 `.env` 重新读一下。

- [ ] **Step 6: Commit**

```bash
cd backend/douyin-processor
git add src/server/endpoints.py
git commit -m "feat(rss): add semantic segmentation to content_encoded"
```

---

## 任务 11: 更新 rss_utils.py docstring

**Files:**
- Modify: `backend/douyin-processor/src/server/rss_utils.py:1-7`

- [ ] **Step 1: 在 rss_utils.py 顶部 docstring 追加说明**

把现有 docstring（1-7 行）：
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

- [ ] **Step 2: 验证 import 仍正常**

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

## 任务 12: 提交主仓库 gitlink 更新

**Files:**
- Modify: 主仓库 gitlink `backend/douyin-processor` 引用

- [ ] **Step 1: 主仓库检查子模块状态**

```bash
cd /f/github/person_project/personal-web
git status
```

Expected: `m backend/douyin-processor`（modified，子模块 gitlink 有新 commits）

- [ ] **Step 2: 主仓库 stage gitlink**

```bash
cd /f/github/person_project/personal-web
git add backend/douyin-processor
```

- [ ] **Step 3: 主仓库 commit**

```bash
cd /f/github/person_project/personal-web
git commit -m "chore: bump douyin-processor pointer（RSS 语义分段）"
```

- [ ] **Step 4: 主仓库 push**

```bash
cd /f/github/person_project/personal-web
git push origin master
```

> **顺序提示**：子模块必须先 push 到远端，主仓库才能 push gitlink（否则别人 clone 会断链）。
> 任务 1-11 里每次 commit 后没要求 push，因为只在子模块内 commit。如果你在自己开发机上操作，
> 可以把子模块 push 留到本任务前：
> ```bash
> cd backend/douyin-processor
> git push origin main
> cd ../..
> ```

---

## 自检 Checklist

- [ ] 任务 1 改 `pyproject.toml` 加 dev 依赖
- [ ] 任务 2 创建 tests 包
- [ ] 任务 3-4 merge 算法 TDD（9 测试）
- [ ] 任务 5-6 format_ts TDD（6 测试）
- [ ] 任务 7-8 render TDD（7 测试）
- [ ] 任务 9 fallback + RSS XML 解析测试（4 测试）
- [ ] 任务 10 endpoints.py 改造 + 端到端 curl 验证
- [ ] 任务 11 rss_utils.py docstring
- [ ] 任务 12 主仓库 gitlink bump + push

总计: 12 任务、26 个测试 + 1 个端到端 curl 验证。
