# MA 关联与长合集修复方案

> 已停止：用户随后批准目录与 MA 解耦，本方案仅保留历史背景，不再执行 MA 维护。实际试跑结果见 ma-repair-result.md。

2026-10-20：用户已明确批准不做备份，仅通过 MA 官方接口刷新缺少关联的120首；先验证小妃摇篮曲7首，再处理其余113首。长合集500首修补明确暂不执行。不得停止/重启MA、改镜像、修改音频或刷新其他曲目。

## 已确认事实

- 7 个当月合集缺失 120 首专辑关联：81+12+7+2+11+3+4；本地 album/albumartist/tracknumber 均完整，曲目详情 API 也返回 album=null，排除仅列表接口漏字段。
- 1106/3000 首两个合集关联完整；MA 2.8.2 AlbumsController.get_library_album_tracks 调用 get_library_items_by_query 时未传 limit，继承默认500。filesystem_local.get_album_tracks 也复用同一方法，换来源 URI 不解决限制。
- MA 的官方上游报告 https://github.com/music-assistant/support/issues/6189 同样记录此500首问题，专辑 API 没有 limit/offset 参数。
- MA 运行中 library.db 对外部 SQLite 连接独占锁定（只读连接 timeout=2 查询返回 database is locked），不能对活跃数据库作未经验证的文件复制或绕过锁备份。

## 具体方案

1. 用户选择不备份，直接在线执行已限定的专辑关联刷新；无需停止或重启MA。
2. 从 kids 当前 done 合集按精确文件路径列出缺失关联项，仅120首。通过官方 music/refresh_item(media_item=原library曲目URI) 重读本地文件、恢复关联，先单独验证小妃摇篮曲缺失的7首，再串行处理其余113首。每首刷新后读回专辑及曲序，不成功就记录并停止该合集；不进行全库删除重建，不用相似标题猜测。
3. 【暂不执行，待后续独立授权】保留MA版本，采用可回滚、固定2.8.2的兼容镜像修补，而非临时修改运行中容器：在 controllers/media/albums.py 的 get_library_album_tracks 内 get_library_items_by_query 调用显式加入 limit=0。MA helpers/database.py 对limit=0不附加SQL LIMIT，因此表示返回完整关联曲目。只修改此专辑查询，不改变所有查询的默认500。镜像重建时核对源方法位置及精确原文，不匹配即失败。

核心补丁：

```diff
 return await self.mass.music.tracks.get_library_items_by_query(
     extra_query_parts=["WHERE album_tracks.album_id = :album_id"],
     extra_query_params={"album_id": db_id},
+    limit=0,
 )
```

## 验证与回滚

- 在隔离验证中使用超过500条的数据库结果验证完整返回和排序；小合集行为保持不变。
- 新镜像加载后，查询两个长合集应返回1106、3000首，文件集合与曲序均与NAS匹配。
- 缺失关联的7个合集分别达到420/97/8/20/91/16/50首；确认音频文件内容与mtime未变。
- 编号歌单仅从kids当月done来源重新生成；不修改编号规则，不把3000首明细传给ESP32，不额外创建播放列表。
- 完整播放队列的验证需选择设备及测试时间，避免未经确认打断用户正在播放的内容；检查队列数和第501首/末首，不能仅靠目录API宣称播放完成。
- 如MA兼容补丁失败，切回原镜像；如索引修复需撤回，停MA恢复备份后启动。备份中可能有连接信息，保留NAS本地，不上传Git。

## 已接受的执行范围

用户原文：“不用备份吧，只刷新缺少关联的120首。先用《小妃摇篮曲》的7首验证，再处理其余曲目，逐项检查专辑和曲序。2先不做”。因此仅修复关联；长合集查询补丁、镜像更新、重启、队列播放测试均不执行。通过已有 kids 容器配置调用官方 MA API，不上传本地 backend 源码。
