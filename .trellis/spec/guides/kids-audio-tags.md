# Kids catalog 历史标签整理契约

适用 backend/kids-catalog/src/audio_tags.py、tag_files.py、tag_audio.py。

- 默认预览；--apply 必须指定扫描目录外备份目录。仅处理根目录的直属合集与 NNN-标题 MP3/M4A。
- 只补缺失；现有 album/title/tracknumber 冲突整文件跳过，多 albumartist 或重复曲序整合集跳过。不得在未获用户要求时加入强制覆盖。
- 新下载器行为保持独立：当前工具不在下载任务里自动调用。
- 发布前完整备份、同步 manifest、验证源文件未变；同目录临时副本经标签读回后才 os.replace。恢复验证路径、备份哈希和现文件哈希。
- 不跟随链接；无编号不猜顺序；不伪造 MusicBrainz ID；哆咪音频仅为无可靠创作者的整理兜底。
- Windows fsync 需可写句柄 rb+，只读句柄会报 Bad file descriptor；pytest basetemp 必须在项目盘。
- 测试必须断言 applied，不能只比较修改前后音频哈希（失败而未修改也会相等）。
- NAS/MA 实际扫描与喇叭验收不能用本地标签测试代替。操作步骤见 docs/已下载音频补标签.md。

- 合集 artist 来源必须包含可读的未编号音频；重复曲序统计必须包含损坏音频的有效文件名编号。二者独立收集，避免提前 continue 丢失信息。Linux 需同步备份目录项及发布后的音频父目录；Windows 不具备该 POSIX 接口。
