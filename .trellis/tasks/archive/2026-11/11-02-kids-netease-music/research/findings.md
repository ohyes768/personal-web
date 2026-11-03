# 网易云音乐接入可行性研究（2026-11-02 实测）

全部结论来自真实 HTTP 请求，非文档推断。环境：macOS，Python urllib 直连。

## 1. 可用接口（全部免登录、免签名、免 Cookie）

| 用途 | 接口 | 实测结果 |
|---|---|---|
| 歌单元数据 + 曲目 ID 全量 | `GET https://music.163.com/api/v3/playlist/detail?id={id}` | `playlist.name`、`playlist.trackCount`、`playlist.trackIds[]`（实测 965 首歌单 **965 个 id 全部返回**，无截断） |
| 歌单内嵌曲目（仅前 10 首） | 同上，`playlist.tracks[]` | 只有 10 首，**不可作为完整曲目源** |
| 专辑元数据 + 曲目全量 | `GET https://music.163.com/api/v1/album/{id}` | `album.name`、`album.size`、`songs[]` **一次性全量返回**（实测 194 首、742 首、162 首均完整，无分页） |
| 曲目详情 | `GET https://music.163.com/api/song/detail/?ids=[...]` | 返回 `id/name/fee`；**单批上限 200**，传 300 只回 201，传 965 返回 0 |
| 播放直链 | `GET https://music.163.com/api/song/enhance/player/url?ids=[...]&br=128000` | `data[].url` 即 mp3 直链；**单批上限 200**（传 500/1000 只回 200） |

请求头只要 `User-Agent: Mozilla/5.0` + `Referer: https://music.163.com/`。

### 失效的接口（不要用）

- `GET /api/album/{id}` → `songs` 恒为空数组（**必须用 `/api/v1/album/{id}`**）
- `GET /api/v3/album/{id}` → 404
- `GET /api/song/enhance/player/url?id={id}`（单数 `id`）→ `{"msg":"参数错误","code":400}`，**必须用 `ids=[...]` 数组**
- `GET /api/v1/player/url` → 404
- `GET /api/song/detail/?id={id}&ids=[{id}]` → `privilege` 字段全为 null，**必须用纯数组 `ids=[...]`**

## 2. 付费判定：`fee` 字段（关键结论）

`/api/song/detail/?ids=[...]` 返回的 `fee` 字段是唯一可靠的付费信号：

| fee | 含义 | player/url 实测 |
|---|---|---|
| `8` | 免费可下 | `code=200`，返回 mp3 直链 |
| `1` | VIP/付费 | `code=-110`，**无 url** |

实测样本（歌单「热歌榜」200 首）：`(fee=8, code=200) × 71`、`(fee=1, code=-110) × 129`，**完全对齐，无例外**。

样本（歌单「网易云音乐×Gamma」965 首）：`(8,200) × 960`、`(1,-110) × 5`。

样本（专辑「睡前故事」742 首）：全部 `(8,200)`。

⚠️ **早期误读更正**：曾用 `zip(player_url.data, songs)` 对齐数据得出「fee=8 不可下载、fee=1 可下载」的相反结论。`player/url` 的返回顺序**不保证**与请求顺序一致，**必须按 `id` 建字典对齐**。这个坑要在实现里明确规避。

### `fee` 语义边界

- 网易云 `fee=8` 表示「无需付费即可播放/下载」（免费或已授权），`fee=1` 表示 VIP 需购买。
- `privilege` 字段在 `/api/song/detail/` 下**全为 null**，不可用；只有 `/api/v1/album/` 内嵌的 `songs[].privilege` 有值（`st=-200` 表示不可用）。**统一以 `fee` + `player/url` 的 `code` 为准。**
- `fee=0` 的曲目（如部分专辑内嵌歌曲）在 `player/url` 下返回 `code=404`（曲目不可用），不可下载。
- 结论：**不下载判定 = `player/url` 返回无 url**（`-110`=VIP 付费、`404`=无音源）。逐条跳过并给出原因。

## 3. 下载可用性

- 直链下载**不需要 Referer**，只要 `User-Agent`。
- 返回文件是标准 mp3，magic 为 `ID3`（或 m4a 的 `ftyp`）。
- `br` 可选：`128000`→约 4MB/首，`320000`→约 10MB/首，`999000` 实际降级到 320k。**建议用 128k 控制体积**。
- 端到端实测（真实儿童歌单「婴儿哄睡必听」39 首）：**下载成功 33 首，6 首 VIP 跳过，共 62.7MB，全部文件校验通过**。
- 更大样本实测（965 首歌单）：960 首成功、5 首跳过。

## 4. 限流

- 连续 20 次 `player/url` 请求全部 200，无 429、无验证码。
- 单批 200 首的 `player/url` 请求耗时约 1.0s。
- 建议仍加 0.3–0.5s 间隔，与现有 `Downloader.throttle_seconds=1.0` / `page_pause_seconds=0.3` 口径一致。

## 5. 链接格式

实测可用：

- `https://music.163.com/playlist?id={id}`
- `https://music.163.com/album?id={id}`
- `https://music.163.com/#/playlist?id={id}`（hash 路由，需先剥 `#`）
- `https://y.music.163.com/m/playlist?id={id}`（移动版）
- `https://music.163.com/m/album?id={id}` → 302 到 `y.music.163.com/m/album`，**解析时直接取 query 的 `id` 即可，不跟随重定向**

**不支持**：

- 短链 `https://163.cn/xxxx` → SSL `UNEXPECTED_EOF_WHILE_READING`、HTTP 502，**当前网络环境不可达，不纳入本期支持范围**。
- 单曲链接 `music.163.com/song?id=` → 明确拒绝（与现有平台口径一致）。

## 6. ID 冲突（PRD 点名风险，已确认）

**歌单 ID 与专辑 ID 空间重叠**。实测 `id=2884035`：

- `/api/v3/playlist/detail?id=2884035` → 歌单「原创榜」
- `/api/v1/album/2884035` → 专辑「소녀괴담 OST」（2 首）

同一个数字既是歌单又是专辑。`albums` 表主键是 `(platform, album_id)`，`platform` 是平台名，两种类型共用一个平台名会撞库。

**解决方案**：用不同的 `platform` 标识区分类型，例如 `网易云歌单` / `网易云专辑`。这样 `(platform, album_id)` 天然唯一，且不改表结构、不影响已有喜马拉雅/蜻蜓数据。

> 备选：把 `album_id` 存成 `pl:123` / `al:123`。但 `album_id` 会被 `Downloader.list_tracks(platform, album_id)` 直接用于拼 URL，加前缀会把 URL 拼接逻辑搞脏。**采用不同 platform 名**更干净。

## 7. 目录与身份（现有机制复用）

- `Downloader.album_dir()` = `music_dir / sanitize_filename(album_title)`，**不含 platform**。两个不同平台同名专辑会落到同一目录 → 现有 `device_candidates()` 已有「本月多个合集对应同一下载目录」检查会报错。
- 网易云歌单标题常含 `|`、`·`、空格等字符，`sanitize_filename` 会保留这些（只去掉 `\ / : * ? " < > |` 及控制字符）。注意 `|` 会被替换掉。
- 曲目标题同理，需过 `sanitize_filename`。

## 8. 前端

- `apps/kids-catalog/app/page.tsx` 导入框 placeholder 现为「粘贴专辑链接（喜马拉雅 / 蜻蜓FM）」，需加网易云。
- `sale_type` 语义现为 `0=免费 / 1=会员畅听 / null=付费未知`。网易云歌单是**混合付费**（同张歌单里免费曲和 VIP 曲混排），**无法在专辑级别判定**。建议网易云统一用 `sale_type=null`（前端已渲染「付费未知」徽标），实际逐曲可用性由下载结果体现。
- `import_album` 的 `sale_type=1` 会触发整张跳过（`skipped_paid`），网易云不能走这条路。

## 9. 未知/待定

- 网易云曲目的 `artist` 字段可用于 tag，但本期**不做 tag 写入**（`audio_tags.write_missing` 只补空标签，且目录生成不依赖 tag）。
- 网易云 mp3 自带 ID3 tag（下载的 童声版 文件 magic `ID3`），现有 `audio_tags.scan` 能识别；但 `audio_tags` 属于独立功能线，本期不动。
- 未测试：付费专辑链接（`fee` 全 1）在预检阶段的行为——**设计上不做专辑级付费拦截**，只在逐曲下载时跳过。
