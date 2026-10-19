# 设备合集目录设计

沿用已确认 PRD：下载 → 手动生成 → 曲目数升序编号 → 版本与编号解析。不做定时发布、历史快照或播放列表。

## 数据与边界

新增 device_collections.py，负责正式 MP3/M4A 扫描、完成清单、排序和 SQLite 当前快照。稳定内部 ID 从直属目录相对路径生成；同曲数按 ID 排序。NAS 文件只读，复用 audio_tags.open_audio 验证，拒绝链接、嵌套音频、临时或损坏文件。完成清单保存文件名、size、mtime_ns，变化后须重新完成下载或人工确认。

Catalog 下载开始登记独立状态，成功后保存完成清单；生成前迁移现存 done jobs（数量必须与实际一致），不随候选清理。历史无记录目录以单次明确确认操作纳入，不自动猜测完成。

MA 使用环境变量 KIDS_MA_URL、KIDS_MA_TOKEN 与 KIDS_MA_MUSIC_ROOT，经 POST /api 读取 music/tracks/library_items 的分页结果。通过 album_tracks(in_library_only=false) 复核整张专辑实际展开，避免额外云端曲目。只使用 filesystem_local 映射，按规范化后的相对文件路径与 track.album 分组，要求精确文件集合、唯一专辑、有效 URI 和正确曲序，不以名称猜测。网络与认证错误不回显密钥或原始响应。

## 接口

- GET /api/collections：当前公开快照、最近生成状态、跳过报告。
- POST /api/collections/generate：后台生成，202；已有生成任务则 409。
- POST /api/collections/confirm：请求 folder，明确确认历史合集已完整，验证后保存文件清单；不修改音频。
- GET /api/device/v1/collections：schema_version、revision、generated_at、items[number,title,track_count]，无服务器路径/凭据。
- GET /api/device/v1/collections/by-number/{number}?revision=...：返回 media_type=album 与 ma_media_uri；旧版本 409、未知编号 404、MA 目标不可用 503。

SQLite 独立表存储完成依据、生成租约和当前快照。构建在事务外，发布为单事务；generation 状态跨进程互斥并对中断任务超时恢复。无可发布合集/整体失败不覆盖旧快照。文件、完成状态在发布前复核；最大 500 项、标题 256 UTF-8 字节、目录响应 128 KiB，超限失败不截断。

## 页面

沿用现有暖色样式和下载列表，新增设备歌单区、生成按钮、编号/名称/曲目数列表、跳过原因和历史完整确认。轮询仅生成过程中启用，错误保留旧内容。Next 现有 /api/kids/:path* 代理复用。

## 环境事实与部署

NAS MA 实际镜像为 2.8.2；两个容器均挂载同一音频目录到 /music。MA API 实测返回 401，尚缺连接凭据，禁止凭本地测试宣称真实 MA/设备验收完成。固件及 HA 在关联工程协作，本轮不修改。回滚代码后原 albums/jobs 保持兼容，新增表可保留。
