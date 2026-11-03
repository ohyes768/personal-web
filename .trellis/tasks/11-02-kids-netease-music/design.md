# 技术设计：Kid 支持网易云音乐链接下载与设备歌单

## 1. 边界

在现有手动导入入口（`link_import.parse_album_link` / `probe_album` / `downloader.Downloader`）上**新增第三个平台**，复用现有下载目录、下载台账、完成确认、设备歌单候选与发布链路。

**不做**：不新建歌单生成系统、不改 MA/设备发布机制、不做网易云账户/会员/私人歌单同步、不绕过付费或访问限制（VIP 曲目逐条跳过）、不做专辑级年龄筛选。

**复用边界**：只扩展 `link_import.py` 和 `downloader.py` 两个文件的平台分派，加少量前端文案；`main.py` 的 `Catalog`/队列/候选逻辑**零改动**（网易云 `sale_type=null`，不触发 `skipped_paid`）。

## 2. 平台标识与身份

新增两个平台常量：

```
NETEASE_PLAYLIST = "网易云歌单"
NETEASE_ALBUM    = "网易云专辑"
```

**为什么用两个而不是一个**：`albums` 表唯一键是 `(platform, album_id)`，而网易云的歌单 ID 与专辑 ID **空间重叠**（实测 `2884035` 既是歌单「原创榜」又是专辑「소녀괴담 OST」）。用两个 platform 名让 `(platform, album_id)` 天然区分，不改表结构、不动历史数据。

`platform` 字符串同时是 `Downloader.list_tracks` / `resolve_url` 的分派依据：

```
"网易云" in platform  →  网易云分支
```

再按 `album_id` 内部编码区分类型。**不采用 `pl:123`/`al:123` 前缀方案**——`album_id` 会直接参与 URL 拼接，加前缀会污染下载逻辑。

### album_id 编码

`album_id` 存**纯数字**（如 `"3778678"`），类型信息由 platform 承载。但 `Downloader` 只收到 `(platform, album_id)`，所以靠 platform 判断：

```python
def list_tracks(self, platform, album_id):
    if "喜马拉雅" in platform: ...
    if "蜻蜓" in platform: ...
    if NETEASE_PLAYLIST in platform: return self._list_netease_playlist(album_id)
    if NETEASE_ALBUM in platform:    return self._list_netease_album(album_id)
```

两个 platform 字符串都含「网易云」，但 `网易云歌单` 不含 `网易云专辑`，故用**精确相等**判断，避免顺序歧义。

## 3. 链接解析

新增正则（放在 `link_import.py`）：

```python
_NETEASE_PLAYLIST = re.compile(
    r'^(?:https?://)?(?:[\w-]+\.)*music\.163\.com/(?:m/)?playlist\?id=(\d+)', re.I)
_NETEASE_ALBUM = re.compile(
    r'^(?:https?://)?(?:[\w-]+\.)*music\.163\.com/(?:m/)?album\?id=(\d+)', re.I)
```

**关键点**：

1. **hash 路由**：用户复制的是 `https://music.163.com/#/playlist?id=3778678`，`#` 后面的 `/playlist?id=` 不是 path。**解析前先剥离 `#` 及其后内容再提取 query**。实现上：把 `#` 之前的部分作为基础，`#/playlist?id=X` 走单独分支——取 `#` 之后 query 里的 `id`，再用 `playlist`/`album` 关键字判定类型。
2. **scheme 缺省**：现有 `parse_album_link` 已有 `if "://" not in text: text = "https://" + text` 的兜底，沿用。
3. **子域名**：`music.163.com` / `y.music.163.com` / `m.music.163.com` 都用 `[\w-]+\.)*` 覆盖。
4. **`m/` 前缀**：移动版路径 `/m/album`、`/m/playlist`。
5. **单曲拒绝**：`music.163.com/song?id=` 命中 `_NETEASE_SINGLE` → 抛「单曲链接不支持」。
6. **短链 `163.cn`**：实测 SSL 不可达，**明确拒绝并提示用完整链接**，不做跟随重定向（避免 SSRF 与不稳定行为）。

**解析优先级**：先查网易云两个正则 → 再查喜马拉雅 → 再查蜻蜓 → 最后单曲/无法识别报错。

## 4. 预检（probe）

`probe_album(platform, album_id)` 新增网易云分支。

### 歌单

```
GET /api/v3/playlist/detail?id={id}
```

- `playlist.name` → 标题
- `playlist.trackCount` → 曲目数（实测与 `trackIds` 长度一致，965 首一致）
- `playlist.trackIds` → 完整曲目 ID 列表
- `code == 404` → `LinkImportError("未找到该网易云歌单")`

### 专辑

```
GET /api/v1/album/{id}
```

- `album.name` → 标题
- `album.size` → 曲目数
- `songs[]` → 完整曲目列表（实测一次全量，无需分页）
- `code == 404` → `LinkImportError("未找到该网易云专辑")`

### sale_type

**统一返回 `sale_type=None`（付费未知）**。理由：网易云歌单是**混合付费**（同一张歌单里免费曲与 VIP 曲混排，实测 39 首里 33 免费 6 VIP），专辑级无法判定。若填 `sale_type=1` 会触发 `Catalog.queue` 的整张跳过，直接废掉功能；填 `0` 会误标「免费」。

前端 `sale_type==null` 已渲染「付费未知」徽标，无需改前端渲染逻辑。

### 返回结构

```python
{
  "platform": "网易云歌单",   # 或 "网易云专辑"
  "album_id": "3778678",
  "title": "歌单名",
  "url": "https://music.163.com/playlist?id=3778678",   # 专辑为 /album?id=
  "sale_type": None,
  "track_count": 965,
}
```

## 5. 下载（Downloader）

### 5.1 曲目列表

**歌单**：`trackIds` 已全量，但只有 ID 没有标题 → 用 `/api/song/detail/?ids=[...]` 批量补标题。

**分批**：单批上限 **200**（实测传 300 只回 201、传 965 回 0）。实现用 `PAGE_SIZE = 200` 分批 + `page_pause_seconds` 间隔。

**顺序**：`song/detail` 返回顺序**与请求顺序一致**（实测校验通过），所以按 `trackIds` 顺序分批即可保持歌单原始顺序。

**专辑**：`/api/v1/album/{id}` 的 `songs[]` 自带 `id` + `name`，**无需二次请求**，直接映射。

```python
Track(track_id=str(song['id']), title=song['name'], ext='mp3')
```

### 5.2 直链解析

```
GET /api/song/enhance/player/url?ids=[...]&br=128000
```

- 批量（≤200）拿一批曲目的直链，**按 id 建字典**。
- ⚠️ **返回顺序不保证与请求一致**，必须 `{x['id']: x for x in data}` 对齐。这是研究阶段踩过的坑。
- `code == 200` 且有 `url` → 可下载
- `code == -110` → VIP/付费受限 → **skip**
- `code == 404` → 无音源/不可用 → **skip**
- 无 url → skip

**为什么用批量接口而不是逐曲单查**：逐曲单查 N 次 HTTP；批量 200 首一次 1.0s。

**为什么不用 `/song/media/outer/url?id={id}.mp3`**：该接口对同一 id 在不同请求间返回不一致（实测 347230/1824045033/145269 返回 302 到 `/404`，而 33894312 正常），不能作为判据。

### 5.3 下载

复用现有 `_download_file(url, dest)`（`.part` 临时文件 + 原子改名）。实测网易云直链**不需要 Referer**，但现有函数硬编码了 `Referer: QT_REFERER`（蜻蜓的）。改为**按平台选 Referer**，网易云用 `https://music.163.com/`。

### 5.4 跳过原因

现有 `DownloadReport` 只有 `downloaded/skipped/failed` 计数，没有逐条原因。**R2 要求「逐条跳过，显示可理解的原因」**。

扩展 `DownloadReport` 增加 `skip_reasons: dict[str, int]`（曲目名 → 次数）？还是更简单的 `skipped_details: list[dict]`？

**选择**：在 `DownloadReport` 增加 `skip_reasons: list[dict]`（`{title, reason}`），由 `main.py` 拼进 job 的 `reason` 字段（`jobs.reason` 是自由文本，已有「完成 N，跳过受限 M，失败 K」这类拼接）。这样前端现有 `x.reason` 展示即可，无需改前端协议。

原因文案：
- `-110` → `VIP 付费，无音源`
- `404`/无 url → `平台无音源`

**失败与跳过必须区分**（R2：「网络或接口失败应如实报告，不能当作成功下载」）。现有 `_download_one` 已区分：HTTP 401/403 → skipped，其他异常 → failed。**但网易云直链 403/404 其实是「音源失效」而非网络故障** → 网易云分支把 403/404 也归为 skip（音源不可用），其余（超时、连接错误、5xx）归为 failed。

## 6. 与现有链路的对接

| 环节 | 改动 |
|---|---|
| `parse_album_link` | 新增网易云分支，返回 `(platform, album_id)` |
| `probe_album` | 新增网易云分支 |
| `Downloader.list_tracks` | 新增网易云分支 |
| `Downloader.resolve_url` | 新增网易云分支（批量取直链后按 id 返回） |
| `Downloader._download_one` | 网易云 403/404 → skip |
| `Downloader.album_dir` | 不变（`music_dir/sanitize(title)`） |
| `main.py` `Catalog` | **不变**（`sale_type=None` 不触发 `skipped_paid`；`import_album`/`queue`/`_run_download` 全部通用） |
| `device_collections.py` | **不变** |
| 前端 `page.tsx` | placeholder 文案加「网易云音乐」 |

### resolve_url 的批量化问题

现有 `Downloader` 接口是**逐曲** `resolve_url(platform, album_id, track)`。若逐曲调用 `player/url`（每次 1 首），200 首歌单要 200 次请求。

**方案**：在 `Downloader` 内加一个**按批次预取直链**的缓存：

```python
def _netease_urls(self, album_id, track_ids) -> dict[str, str|None]
```

`list_tracks` 时（或 `download_album` 开始时）一次性批量取回，存 `self._netease_url_cache[(album_id)] = {track_id: url_or_None}`，`resolve_url` 从缓存取。

**缓存生命周期**：按 `album_id` 缓存，`download_album` 开头清空该 album 的缓存。

**直链时效**：`player/url` 返回的 `expi` 字段是 1200 秒（20 分钟）。批量取回后 20 分钟内有效。200 首下载每首间隔 1.0s = 200s，加落盘时间，远在有效期内。但为稳妥，**批次取回后若缓存超过 10 分钟则重新获取**。

更稳的做法：**边下边取**——每 20 首一批，取一批直链，下这一批，边下边续。但这会让 `resolve_url` 有副作用。

**最终选择**：**分批预取 + 下载**。`download_album` 内部把流程改成：
1. `list_tracks` → 全部曲目
2. 每 200 首一批：取直链 → 下载该批 → 下一批

这样每批的直链都是新鲜的（20 分钟内），且请求数 = ceil(N/200)。

实现上给 `Downloader` 加一个可选的批量下载路径，**不破坏现有 `resolve_url` 逐曲契约**（喜马拉雅/蜻蜓仍走原路径）：

```python
def download_album(self, platform, album_id, album_title, on_progress=None):
    if "网易云" in platform:
        return self._download_netease(album_id, album_title, on_progress)
    ... # 原逻辑不变
```

`_download_netease` 内部：
```python
tracks = self._list_netease(album_id)   # 歌单/专辑分派
album_dir = self.album_dir(platform, album_title)
album_dir.mkdir(parents=True, exist_ok=True)
report = DownloadReport()
for batch in chunks(tracks, 200):
    urls = self._netease_batch_urls([t.track_id for t in batch])
    for index, track in enumerate(batch, start=offset+1):
        report = self._download_one_with_url(platform, track, index, album_dir, report, urls.get(track.track_id))
        ...
    time.sleep(self.page_pause_seconds)
```

## 7. 兼容性与回归

- **喜马拉雅/蜻蜓**：代码路径完全不动，只在 `list_tracks` / `resolve_url` 的 if 链末尾加分支。现有测试全绿是硬要求。
- **历史下载内容**：`albums` 表既有行不动；`device_collections` 的 completion 台账按 folder 记录，网易云复用同一 folder 规则。
- **同名冲突**：网易云标题若与已有喜马拉雅专辑同名 → `album_dir` 相同 → `device_candidates()` 现有检查「本月多个合集对应同一下载目录，请核对合集名称」会拦下。**沿用现有行为，不额外造规则**。
- **`title` 含特殊字符**：网易云标题常含 `|`（如「网易云音乐×Gamma达成深度合作 | 立即畅听」）。`sanitize_filename` 会把 `|` 替换掉（`INVALID_FILENAME` 含 `|`）。这会导致**同名不同 `|` 的两个歌单映射到同一目录** → 被现有同名检查拦下。行为可接受，但要在 UI 上让用户能看出差异——**现有 UI 只显示标题**，两个歌单标题只差 `|` 会看起来一样。

  **改进**：`probe_album` 返回的 `title` 不做处理（保持原样展示），但 `album_dir` 已 sanitize。**这是现有喜马拉雅/蜻蜓的同样行为**，不新增特殊处理。

- **重复导入幂等**：`albums` 表 `unique(platform, album_id)` + `import_album` 的 `on conflict do update` → 同一歌单重复导入更新同一行，`queue()` 对已有 job 幂等返回。**网易云歌单/专辑同 ID 但 platform 不同 → 两行，各自独立**，符合预期。

## 8. 失败与回滚

- **回滚点**：删除 `link_import.py` 与 `downloader.py` 的网易云分支 + 前端文案，即完全回到现状。数据库无 schema 变更（复用 `platform`/`album_id` 字符串列），**无迁移、无回滚脚本**。
- **风险点**：
  - 网易云改接口 → 解析失败 → 抛 `LinkImportError`（用户可读），不 500。
  - 网易云限流 → 目前实测无限流，但保留 `throttle_seconds` / `page_pause_seconds` 间隔。若未来触发 429 → 当前 `_download_one` 归为 failed，job 显示失败原因。**不实现退避重试**（超出本期范围，且现有喜马拉雅/蜻蜓也没有）。
  - 直链 20 分钟过期 → 分批下载规避。

## 9. 测试策略

**后端 pytest**（`backend/kids-catalog/tests/`）：

1. `test_link_import.py` 扩展：
   - 网易云歌单/专辑链接解析（含 hash 路由、移动版、缺 scheme、尾斜杠、query 额外参数）
   - 单曲链接拒绝
   - 短链 `163.cn` 拒绝
   - 平台识别互不串台（喜马拉雅/蜻蜓链接不被误判为网易云）
   - `probe_album` 网易云分支：成功 / 404 / 网络失败 / `track_count` 正确 / `sale_type is None`
2. `test_downloader.py` 扩展：
   - 歌单曲目列表（分批 200、顺序保持、标题正确）
   - 专辑曲目列表（一次全量）
   - 直链按 id 对齐（**构造乱序返回，验证按 id 匹配而非按序**——防回归关键用例）
   - `-110` → skip、`404` → skip、网络异常 → failed
   - `skip_reasons` 内容正确
   - 落盘文件名 `NNN-标题.mp3`
3. `test_api.py` 扩展：
   - `POST /api/albums/import` 网易云链接 → 200 → job 状态 `queued`
   - 网易云歌单下载完成 → 成为设备歌单候选
   - 喜马拉雅/蜻蜓导入回归

**前端**：`apps/kids-catalog` TypeScript 检查 + 生产构建。

## 10. 交付顺序

1. `link_import.py`：解析 + 预检（纯函数，好测）
2. `downloader.py`：曲目列表 + 直链批量 + 下载 + 跳过原因
3. `main.py`：仅在需要展示跳过详情时改 `reason` 拼接
4. 前端文案
5. 测试 + 构建
