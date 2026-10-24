# 技术设计：kids 曲目管理

## 边界

- 后端只动 `src/main.py`（Catalog 两个方法 + 两个路由 + 1 个 Body 模型 + queue 可重试集合）。
  ⚠️ main.py 有并行会话未提交改动（`_device_candidate_rows` / `/api/collections` 两处，设备合集
  台账功能），提交时用 `git apply --cached` 只暂存本次 hunks，双方改动互不包含。
- 前端动 `app/page.tsx`（卡片入口 + 下载按钮 partial 可点）、新增 `app/track-manager.tsx`（弹窗）、
  `app/globals.css`（弹窗样式）。`device-playlist.tsx` / `candidate-picker.tsx` 不动。
- 文件身份 = 磁盘文件名（`001-标题.m4a`），不新建曲目表：目录就是事实源，与设备合集
  `scan()` 的消费方式一致。

## API

- `GET /api/albums/{album_id}/tracks`
  - 专辑不存在 → 404 `专辑不存在`
  - 目录不存在 / 无音频 → 200 `{'tracks': []}`
  - 正常 → `{'tracks': [{'file', 'title', 'size'}]}`，按文件名排序；
    title = 去掉 `NNN-` 序号前缀和扩展名
- `DELETE /api/albums/{album_id}/tracks`，body `{'file': str}`（`DeleteTrackBody`）
  - 专辑不存在 → 404；job 在 queued/running → 409 `正在下载中，请等下载完成后再管理曲目`
  - file 含路径分隔符 / `..` / 非 .mp3 .m4a → 422 `文件名不合法`
  - 文件不存在于专辑目录 → 404 `未找到该曲目文件`
  - 成功 → 200 `{'downloaded_tracks': n, 'size_bytes': s, 'status': ...}`

## 状态机（删除驱动的 job 变迁）

```
删除一首（剩余 n>0）: status→partial, downloaded_tracks=n, size_bytes=Σ剩余,
                      reason='用户删除曲目，剩余 n 首', completions 置 incomplete（update-only）
删除最后一首（n=0） : delete job 行 → 专辑 not_downloaded, 按钮变"下载"
补全下载            : queue() 重试集合 ('failed','needs_authorization') += 'partial'
                      → 删旧 job 重新排队；download_album 对已存在文件跳过，只补缺
```

- `_backfill_sizes` 只在 size 为 NULL 时补算，删除接口总是写入新值，不冲突。
- `import_completed_downloads` 以 `downloaded_tracks==total_tracks` 为证据条件，
  删除后不等 → 不会把缩水的专辑误登记进台账。
- completions.mark_failed：已确认合集删除曲目后发布态失效，设备歌单页显示需重新生成；
  与生成器的 manifest 漂移检测（`record['manifest'] != encoded(scan())`）双保险。

## 前端

- 卡片：done/partial 时下载按钮旁出现「曲目 ✎」入口按钮（title 悬浮说明）。
  partial 的下载按钮文案从"部分完成"（禁用）改为"补全下载"（可点）。
- `TrackManager` 弹窗：受控开关放 page.tsx（state: 管理中的 album）；打开即拉
  `/api/kids/albums/{id}/tracks`；每行曲名 + 大小 + 删除；删除成功后刷新列表并回调
  `load()` 更新卡片徽章；底部固定提示：删除的曲目可通过"补全下载"找回；已生成设备
  歌单的合集需重新生成。遮罩点击 / 关闭按钮退出。
- 样式沿用 globals.css 现有暖白纸基调，弹窗为居中卡片 + 半透明遮罩，按钮复用现有
  类名风格。

## 兼容与回滚

- 纯新增 API + 状态语义扩展（partial 可重试），不改既有接口响应结构；
- 回滚 = revert 提交即可，磁盘文件与 DB 无迁移（无 schema 变更）。
