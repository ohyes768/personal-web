# 设备目录简化设计

## 职责与数据流

Catalog 当月 done 来源 → NAS 正式音频校验与计数 → 曲目数排序 → 当前 revision 目录 → 设备显示 / 编号名称查询。生成与查询不连接 MA。MA 独立负责播放方后续按名称查找和播放。

## 存储与兼容

DeviceCollections(data_dir, music_dir, candidate_source) 保留独立 SQLite 的 completions、publication、generation 表。旧 publication.targets 非空约束保留避免清库或破坏旧部署；新发布将其写成空对象，查询从不读取该字段。旧版本目录的 items 本来就包含编号、名称与曲目数，可直接返回名称，无需迁移 MA URI。

文件清单仍保存 filename/size/mtime_ns。file_order 对既有 NNN-文件名沿用数值顺序以兼容持久化完成依据；普通文件名按名称排序。不再把文件名曲序、标签、MA album/track 字段当作准入条件。

## 并发与错误

初次通过 candidate_source 上下文获取当月 done 白名单后释放锁；扫描不持有 Catalog 写锁。发布前重新获取 Catalog BEGIN IMMEDIATE 锁复核来源，保持到 device DB 提交。统一 Catalog → device 锁序，与下载入队一致。

read() 在显式读事务内获取 publication 和 generation，避免两个 SELECT 跨越一次发布，造成 done 配合旧快照。其余租约、整体替换、失败保留与容量边界沿用现有实现。

## 接口

GET /api/device/v1/collections 的 schema_version=1、revision、generated_at、items[number,title,track_count] 不变。

GET /api/device/v1/collections/by-number/{number}?revision=... 仅返回 revision、number、title、track_count。移除 media_type、ma_media_uri 和503 target_unavailable。未知目录/编号404、旧revision409。该响应是名称映射，不表示可播放性。

管理接口继续 GET /api/collections、POST /generate、POST /confirm。跳过报告只保留 NAS/下载完成/容量类原因，前端生成中提示改为本地音频检查。

## 配置与边界

main.py 不再导入、构造或注入 MusicAssistant 客户端。现有独立 music_assistant.py 工具及部署环境配置保留给后续独立播放接入；它们不参与目录生成/查询。用户的真实 .env 不作修改。

不部署或维护 MA。本轮只完成当前仓库代码、测试和文档；之前的 MA 修复研究保留为历史，并标记暂停，不能当作当前执行清单。
