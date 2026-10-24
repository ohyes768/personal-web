# kids 喜马拉雅下架专辑旧接口兜底下载

## Goal

用户粘贴微信分享的喜马拉雅链接（`m.ximalaya.com/selfshare/albumnew/{id}`）导入失败。诊断结论：
新版曲目接口 `mobile/v1/album/track` 对这批专辑返回 ret=924（"已下架"），但旧接口
`mobile/v1/album/single` 仍在正常服务（专辑 status=1/isPublic=True/isPaid=False，曲目列表、
直链俱全，实测 playUrl64 可下载，`m.ximalaya.com/tracks/{id}.json` 也仍有效）。
本任务：让链接导入与下载在 924 时回退旧接口，并让解析器接住 selfshare 分享链接格式。

实测样本（2026-10-24）：

- 16350309《听，小蜗牛艾玛》西区爱乐，18 曲全免费
- 3715099《谁要跟我去散步》尛甜訫xin，25 曲全免费

## Requirements

1. 链接解析（`src/link_import.py` `_XM_ALBUM`）：接受 `ximalaya.com/(selfshare/)?album(new)?/{id}`
   两种路径（`albumnew`、`selfshare/albumnew`、`selfshare/album`），兼容现有全部格式
   （scheme 缺省、m/www 子域、查询参数、尾斜杠）。
2. 曲目列表兜底（`src/downloader.py`）：新增 `xm_tracks_page(fetch, album_id, page, referer)`
   ——先走 `album/track`，ret=924 时改走 `album/single` 并归一化为 `album/track` 的响应形状
   （曲目项注入 albumTitle、保留 list/totalCount/maxPageId）；两个接口都不可用则原样返回
   924 payload。`_list_ximalaya` 与 `link_import._probe_ximalaya` 的逐页请求统一换用该函数。
3. 预检兜底（`link_import._probe_ximalaya`）：经兜底后仍拿不到数据 → 维持现有
   "该专辑已被平台下架" 报错；付费判定逻辑（首页全付费抽末页复核）不变，直接复用归一化结果。
4. fetch 函数作为参数传入 `xm_tracks_page`（downloader 用 `_fetch_json`，link_import 用
   包了用户可读报错的 `_fetch`），保持现有 monkeypatch 测试方式可用。

## Out of Scope

- `ximalaya_album_available` / `track_total`（榜单采集侧）不改：榜单不应收录下架专辑，
  且 `track_total` 对 924 返回 None 不阻塞。
- `resolve_url`（`tracks/{id}.json`）不改：实测对兜底取到的曲目 ID 仍有效。
- 不实现单曲链接导入（`/sound/{id}` 仍拒绝）。

## Acceptance Criteria

- [ ] `parse_album_link` 对两条真实分享链接（含完整查询参数）返回
      `("喜马拉雅", "16350309")` / `("喜马拉雅", "3715099")`
- [ ] `album/track` 返回 924 时：`probe_album` 能取到专辑名与曲目数；`Downloader.list_tracks`
      能取到曲目列表（mock 测试）
- [ ] 两个接口都返回 924 → 预检仍报"已下架"，下载仍抛 `AlbumOfflineError`（mock 测试）
- [ ] 真实网络验证：两条真实链接走 `parse_album_link → probe_album → list_tracks → resolve_url`
      全链路可用，且实际下载 1 个曲目文件成功
- [ ] 现有全部测试通过（`python -m pytest -q`）

## Notes

- 接口实测记录：`album/single` 响应形状为 `data.album.{title,isPaid,...}` +
  `data.tracks.{list,pageId,pageSize,maxPageId,totalCount}`，list 项含
  `trackId/title/isPaid/playUrl32/playUrl64/playPathAacv164/224`。
