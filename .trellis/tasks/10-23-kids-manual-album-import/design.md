# 技术设计：手动链接导入下载新合集

## 接口调研结论（2026-10-23 实测验证，真实请求逐字段核对）

### 喜马拉雅（复用现有 mobile 接口）

`GET https://mobile.ximalaya.com/mobile/v1/album/track/?albumId={id}&pageSize=30&pageId=1`：

| 字段 | 用途 |
|------|------|
| `ret == 924` | 已下架或不存在（实测不存在专辑也返回 924），拒绝导入 |
| `data.totalCount` | 曲目总数（入目录的 track_count） |
| `data.list[0].albumTitle` | 专辑标题 |
| `data.list[].isPaid` | 曲目级付费标记（专辑级无付费字段，`data` 只有 list/maxPageId/pageId/pageSize/totalCount） |

付费预判：抽首页 30 曲；**首页全 `isPaid=true` 时再抽末页复核**，两页皆全付费 → 整张付费拒绝。
末页复核是为了避免「首页恰好全是免费曲、后面整张收费」被误判为免费专辑（免费专辑实测全量 `isPaid=false`，付费专辑实测 143/143 全 `isPaid=true`）。
真假混合 → 免费专辑（含受限曲目，下载时逐条跳过）。

### 蜻蜓（复用现有 capi 接口）—— 付费判定在专辑级，不在曲目级

- `GET https://i.qingting.fm/capi/v3/channel/{id}`（Referer `www.qingting.fm`）→ `data.title`、`data.v`（版本号）、`data.vip_label`、`data.sale_props`
- `GET https://i.qingting.fm/capi/channel/{id}/programs/{v}?curpage=1&pagesize=30&order=asc` → `data.total`、`data.programs[]`

**实测纠正（初版设计按曲目级 `isfree` 判定，实测语义相反）：**

- 曲目级 `isfree` 缺省即「该键不出现」，出现在 VIP 专辑里时值恒为 `true`，标记的是**VIP 专辑里的免费集**（`sale_props` 列出同一批 id）。
- 真实可下载性实测：`sale_props` 内的节目 HTTP 206 可下，VIP 专辑里其余节目全部 HTTP 401。
- 专辑级 `vip_label == "会员畅听"` ⟺ 网页榜单侧 `sale_type == 1`（实测 9/9 付费专辑命中、5/5 免费专辑无此标签，14 个样本一一对应）。

付费预判：`vip_label == "会员畅听"` → 整张付费拒绝（与采集器 `sale_type == 1` 的跳过口径完全一致）；否则视为免费专辑。
蜻蜓专辑不存在 → capi 返回 HTTP 400，转成「专辑不存在」。

### 链接格式（正则解析）

```
喜马拉雅: ^https?://(?:[\w.]+\.)?ximalaya\.com/album/(\d+)(?:[/?#]|$)
蜻蜓:     ^https?://(?:[\w.]+\.)?qingting\.fm/vchannels/(\d+)(?:[/?#]|$)
```

容忍缺省 scheme（补 `https://`）、www/m/无子域、尾斜杠与查询参数。
其余（含 `sound/`、`radio/` 单曲链接）→ 明确报错「仅支持专辑链接」。

## 数据模型变更

`albums` 表加列（沿用现有 pragma 迁移模式，`main.py:Catalog.__init__`）：

```sql
alter table albums add column source text not null default 'chart'
```

`Catalog.refresh()` 两处改动（`src/main.py:64-79`）：

1. upsert 时写入 `source='chart'`
2. 清理语句从 `last_seen != ?` 收窄为 `source='chart' and last_seen != ?`（albums 与级联 delete jobs 两句都要加条件）

老库存量行迁移后默认 `chart`，语义正确（存量全部来自榜单）。

## 新模块 `src/link_import.py`

```python
class LinkImportError(ValueError):
    """用户可读的导入失败原因（付费/下架/链接不识别）。"""

def parse_album_link(url: str) -> tuple[str, str]        # (platform, album_id)
def probe_album(platform: str, album_id: str) -> dict
    # 返回 {title, track_count, paid, url}；付费/下架/网络失败抛 LinkImportError
```

- `probe_album` 内部限速 `time.sleep(0.2)`，与现有预检同款（防风控）
- platform 取值与现有目录一致：`"喜马拉雅"`、`"蜻蜓FM"`（`Downloader.list_tracks` 按 `in platform` 分派，不能换名）
- 网络失败如实报错（不像榜单采集可保守放行——手动导入失败让用户重试即可）

## Catalog 与 API 变更（`src/main.py`）

### `Catalog.import_album(row) `

1. upsert albums（`on conflict(platform,album_id) do update set title,url,sale_type,track_count,source='manual',last_seen`；
   冲突时**不覆盖** `age_evidence`/`age_confidence`，保留原值）
   - 新插入行：`age_evidence='手动添加'`、`age_confidence='高'`、`sale_type=0`（整张付费已在 probe 阶段拒掉）、`track_count` 写 probe 值、`source='manual'`
   - 冲突行：`source` 翻成 `manual`——用户显式导入过，即便它也出现在当月榜单也要跨月保留
2. 取 album 主键后**直接调用现有 `queue(album_pk)`**：它已经实现了「已有 job 且状态非 failed/needs_authorization → 幂等返回现状」「否则建 queued job 并起下载线程」「sale_type==1 → skipped_paid」，两处复用同一份逻辑，不复制
3. 返回 `{album_pk, job_id, status, reason}`

注意：`refresh()` 的 upsert 对手动专辑也有影响——若手动专辑恰好出现在当月榜单，upsert 会把 source 覆盖回 chart。处理：refresh 的 upsert 不覆盖 source（去掉 `source=excluded.source`，保留原值；新插入行仍写 chart）。下载记录（jobs）不受影响。

### 新端点

```
POST /api/albums/import   body: {"url": "..."}
→ 200 {album_pk, status, reason?}     # status: queued/done/partial/...
→ 422 {detail}                        # 付费/下架/链接不识别（LinkImportError）
```

Pydantic body：`url: str (min_length=8, max_length=512)`。

### 不改动的部分

- `Downloader` 全部复用（`download_album`/`sanitize_filename`/`AlbumOfflineError` 兜底下载中途下架）
- `DeviceCollections`/`device_candidates` 零改动：查询是 `albums join jobs where status='done'`，manual 专辑自动成为合集候选
- `import_completed_downloads`、legacy 记录逻辑零改动（同样基于 join，与 source 无关）
- 设备端 `/api/device/v1/*` 零改动

## 前端改动（`apps/kids-catalog/app/page.tsx`）

header 下加导入条（表单）：输入框 +「获取」按钮：

- 成功：message 显示「《专辑名》开始下载」，复用现有 3s 轮询展示进度
- 失败：显示后端 detail（付费/下架/链接不识别）
- 专辑卡片 badge：`source === 'manual'` 时显示「手动添加」标记
- 手动专辑的年龄行不再展示平台的年龄依据与「高可信」——手动导入不做年龄筛选，
  改为如实显示「用户自主选择 · 不做年龄筛选」，免得「手动添加」标记与年龄依据自相矛盾
- 样式沿用现有紧凑风格，入口常驻头部（用户 UI 偏好：零点击、有主见默认值）

### heading 取值修正

「本月精选」标题与「更新于」时间原取全部专辑 `last_seen` 的最大值。手动专辑的 `last_seen` 是导入时间，
跨月后会把标题从「10月精选」顶成「11月精选」，而榜单其实还是 10 月的。
处理：heading 的 stamp 只取 `source === 'chart'` 的最大 `last_seen`；一张 chart 专辑都没有时退回全部专辑的 max。

## 风险与边界

| 风险 | 处置 |
|------|------|
| 双数据源结构（web 发现 + mobile 下载） | 刻意设计不动（2026-09 调研拍板）；手动导入全程走 mobile/capi，不碰 web 体系 |
| 手动专辑与榜单专辑同名 | `device_candidates` 已有重名 `CollectionError`；导入时不额外拦截（同名概率低，且 sanitize 后才可能撞） |
| 喜马拉雅风控 | probe 与现有预检同款限速；失败如实报错可重试 |
| 前端「本月精选」heading 基于榜单 last_seen | 手动专辑 last_seen 是导入时间，会把 heading 顶到导入当月 → 改为只取 chart 来源的最大 last_seen |
| sqlite 手动迁移 | 沿用 pragma table_info 模式，向后兼容 |

## 测试策略

- `tests/test_link_import.py`：parse_album_link 各格式/缺省 scheme/尾斜杠/单曲链接拒绝；
  probe_album 分支（mock `_fetch_json`）：
  - 喜马拉雅免费（首页全 isPaid=false）、整张付费（首页全 true 且末页复核全 true）、
    混合（首页真假混合）、付费但末页有免费曲（复核后放行）、下架 ret=924
  - 蜻蜓免费（vip_label 缺失）、会员专辑（vip_label=会员畅听 → 拒绝）、专辑不存在（HTTP 400）
- `tests/test_api.py` 增补：import 端点（成功/付费拒绝/下架/非法 url/幂等）；refresh 后 manual 专辑与其 job 仍在
- 前端手动验证 + `pnpm build`
