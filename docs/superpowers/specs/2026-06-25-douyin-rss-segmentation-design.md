# Douyin RSS 订阅源语义分段设计

**日期**: 2026-06-25
**范围**: `backend/douyin-processor`（独立 git submodule）
**作者**: Claude (brainstorming 流程产出)
**状态**: 待用户审阅

## 背景

抖音视频的文字转写已经通过 `/api/rss.xml` 端点（commit `caec055`）输出到 RSS 订阅源（FreshRSS / Feedly / Inoreader）。当前实现把整段转写 `text` 字段平铺到 `<content:encoded>` 里，**没有任何段落结构**，长视频在 RSS 阅读器里阅读体验很差（一眼一坨字、无停顿感）。

**现有数据资产**：`output/{aweme_id}.json` 已经有阿里云 ASR 返回的 `segments` 字段（带 `start_time` / `end_time` / `text` / `confidence`），前端 VideoModal 已经在用 `segments.map()` 渲染。**后端不需重新生成 ASR 数据**，只需把 segments 翻译成分段 HTML 嵌进 RSS。

## 目标

让 RSS 订阅源里的转写呈现为**带起始时间戳的语义段**，阅读体验接近前端 Web 模态框。

**非目标（YAGNI）**：
- 不做 LLM 重分章（成本/延迟不可接受）
- 不做实时重算（RSS 是缓存友好型，5 分钟 TTL 已够）
- 不改前端 Web UI（VideoModal 已经有 segments 渲染）
- 不动 RSS channel 顶层结构（title/link/description 不变）
- 不引入新依赖（标准库 + 现有 `xml_escape` / `cdata_safe` 工具足够）

## 设计

### 4.1 新增 `backend/douyin-processor/src/server/segment_html.py`

#### 函数 1: `merge_segments_to_paragraphs`

```python
def merge_segments_to_paragraphs(
    segments: list[dict],
    gap_threshold: float = 1.5,
    max_chars: int = 120,
) -> list[list[dict]]:
    """把 ASR segments 分组成"段"。

    切段规则（按顺序判断）：
    1. 第一个 segment 开新段
    2. 后续 segment 若满足任一条件则切新段：
       - 跟前一段最后一个 segment 的 end_time 间隔 > gap_threshold
       - 当前段已累积 char 数 ≥ max_chars

    特殊处理：
    - segments 为空 → []
    - segment 缺 text 字段 → 当空串处理（不切段）
    - segment 缺 start_time/end_time → 视为与前一段连续
    """
```

#### 函数 2: `format_ts`

```python
def format_ts(seconds: float) -> str:
    """秒数 → 'MM:SS' 或 'H:MM:SS' 格式。

    0.28 → "00:00"
    75.4 → "01:15"
    3725 → "1:02:05"
    """
```

#### 函数 3: `render_paragraphs_html`

```python
def render_paragraphs_html(paragraphs: list[list[dict]]) -> str:
    """段 → HTML 字符串。

    每段渲染为:
        <p><span class="ts">MM:SS</span> 段内文本</p>

    段内各 segment 的 text 用单个空格 `" "` 拼接。
    多段之间用换行符 `\n` 分隔（不影响 XML 解析，RSS reader 折叠）。
    输出会再经 xml_escape + cdata_safe。
    """
```

### 4.2 修改 `backend/douyin-processor/src/server/endpoints.py`

#### 改动 A: 新增 `_read_output_doc`

替换当前的 `_read_output_text`，返回 segments 字段。

```python
async def _read_output_doc(aweme_id: str) -> Optional[dict]:
    """读 output/{aweme_id}.json，返回 {text, segments}。

    损坏/缺失 → None（单条跳过，不阻塞 RSS feed）。
    """
    try:
        result_file = Path(processor.output_dir) / f"{aweme_id}.json"
        if not result_file.exists():
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

#### 改动 B: RSS 端点循环内的 fallback 链

替换 `endpoints.py:948-968` 的拼装逻辑：

```python
for (aweme_id, st), doc in zip(candidates, docs):
    if doc is None or not doc["text"]:
        continue  # output 损坏/缺失 → 跳过

    # 分段策略（按优先级）
    if doc["segments"]:
        paragraphs = merge_segments_to_paragraphs(doc["segments"])
        body = render_paragraphs_html(paragraphs)
    elif "\n\n" in doc["text"]:
        # 旧数据有预分段 → 按 \n\n 切
        body = "\n".join(
            f"<p>{xml_escape(p.strip())}</p>"
            for p in doc["text"].split("\n\n") if p.strip()
        )
    else:
        # 兜底：整段单 <p>
        body = f"<p>{xml_escape(doc['text'].strip())}</p>"

    items.append({
        # ... 其他字段不变 ...
        "content_encoded": body,
    })
```

**说明**：
- 优先用 segments（启发式合并 + 段头时间戳）
- 旧数据无 segments 但 text 含 `\n\n` → 按 `\n\n` 切
- 都没 → 整段 `<p>`（保持兼容）

#### 改动 C: `_RSS_DEFAULT_LIMIT` 等常量不动

鉴权、限流、缓存策略、错误处理矩阵**全部保持现状**。

### 4.3 不动 `rss_utils.py`

- `build_rss_xml` 已是通用 XML 拼装，content_encoded 字段透传即可
- `xml_escape` + `cdata_safe` 仍负责 HTML/`<![CDATA[...]]>` 安全
- 在 `rss_utils.py` 顶部 docstring 追加一行说明："content_encoded 已分段（见 endpoints.py）"

## 数据流

```
GET /api/rss.xml?token=...&limit=50
  │
  ├─ 1. 鉴权（不变）
  ├─ 2. 拿 statuses（不变）
  ├─ 3. 排序/截前 N（不变）
  │
  ├─ 4. 并发读 output
  │     gather(_read_output_doc(aid) for aid, _ in candidates)
  │     每条返回 {"text": str, "segments": list|None}
  │
  ├─ 5. 拼装 item
  │     ├─ 优先用 segments 走启发式合并 → 段头时间戳 HTML
  │     ├─ fallback 1：text 含 \n\n → 按 \n\n 切
  │     └─ fallback 2：整段 <p>
  │
  └─ 6. build_rss_xml → 200 OK（不变）
```

## 错误处理矩阵

| 场景 | 行为 |
|------|------|
| `output/{id}.json` 不存在 | RSS item 跳过（保留当前行为） |
| JSON 损坏 | RSS item 跳过（保留当前行为） |
| `segments` 字段缺失/为 None | fallback 到 `text`（含 `\n\n` 切） |
| `segments` 字段为空列表 `[]` | fallback 到 `text`（含 `\n\n` 切） |
| 段内 text 含 `<` `&` `]]>` | `xml_escape` + `cdata_safe`（`build_rss_xml` 已做） |
| 单条 RSS item 合并失败 | 该 item 跳过（不影响其他 item） |
| `merge_segments_to_paragraphs` 抛异常 | 同上，单条跳过 |

## 测试

`backend/douyin-processor/tests/test_segment_html.py`（新增文件）。

### 必测场景

1. **`merge_segments_to_paragraphs` 边界**
   - 空输入 → `[]`
   - 单段 → `[[s1]]`
   - 时间间隔 > 1.5s → 切段
   - 字数 ≥ 120 → 切段（边界 119/120/121）
   - 间隔和字数都满足时按间隔先切
   - segment 缺 start_time → 不切段

2. **`format_ts`**
   - `0.28 → "00:00"`
   - `75.4 → "01:15"`
   - `3725 → "1:02:05"`
   - `0 → "00:00"`

3. **`render_paragraphs_html` 转义安全**
   - 段内含 `<script>` → 实体转义成 `&lt;script&gt;`
   - 段内含 `]]>` → CDATA 安全替换
   - 段内含 `&` → `&amp;`

4. **端到端**
   - 模拟 RSS 输出含分段 HTML，`xml.etree.ElementTree` 解析成功
   - 验证 `<p>` / `<span class="ts">` 结构完整

5. **Fallback 行为**
   - 旧数据无 segments → 整段 `<p>`
   - text 含 `\n\n` → 按 `\n\n` 切段

### 不测场景（YAGNI）

- 多说话人分离（阿里云 ASR 单声道不分 speaker）
- 实时重新计算（不热路径）
- RSS 阅读器视觉回归（不接入浏览器自动化）

## 风险 & 缓解

| 风险 | 缓解 |
|------|------|
| 旧 RSS 客户端缓存 5 分钟内仍返回旧 RSS | 5 分钟后自动刷新；用户可在 RSS reader 手动点"刷新" |
| 分段后 RSS 文件变大（多 HTML 标签） | 单条增加 < 1KB，200 条上限下 < 200KB，gzip 后 ~30KB，可接受 |
| FreshRSS CSS 不识别 `.ts` class | 不影响内容正确性，只是时间戳不显红/不显眼；功能仍可用 |
| `merge_segments_to_paragraphs` 边界 bug 导致段落过碎/过长 | 120 字软上限 + 1.5s 硬切 + 完整单测覆盖边界 |

## 不在本次范围

- LLM 分章增强
- 段落标题生成（"② 00:15 论点"）
- Web UI 同步展示分段（前端 VideoModal 已有）
- 新增 RSS 端点（不破坏现有 `/api/rss.xml` 契约）
- 移动端 RSS reader 适配
