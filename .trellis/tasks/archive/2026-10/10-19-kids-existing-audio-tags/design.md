# 技术设计

用户已在对话批准批量整理方案及保守冲突策略。采用 Mutagen 处理真实 MP3/MP4 容器；独立 CLI，不触及在线下载流程。

src/audio_tags.py 负责扫描、字段映射和推导，src/tag_files.py 负责备份/原子发布/恢复，src/tag_audio.py 提供命令入口。扫描限定 root 的直接子目录，不递归猜测任意音频结构；--album 按精确目录名过滤。跨合集同名风险通过 albumartist 提示，不伪造 MusicBrainz ID。

默认 stdout JSON 报告：path/status/current/proposed/changes/conflicts/error。--apply 重新读取当前文件，先制作同目录临时副本，补标签并读回验证；完整备份和带 SHA256 的 manifest 先 fsync，再 os.replace 发布。备份使用每次运行唯一目录。标签冲突整文件不写；同目录多个已有 albumartist 或重复曲序整体跳过，避免拆散或错序。

--restore 从 manifest 恢复原文件，要求 root 与记录一致、路径无穿越/符号链接、备份哈希匹配、当前文件仍为该次修改后的哈希；恢复用临时副本原子替换。重复恢复保持幂等。需要额外磁盘空间：整批备份总大小 + 同时一个最大音频的临时副本。

测试用 FFmpeg 自行生成短 MP3/M4A 固定夹具，比较压缩音频包摘要验证不转码；仅测试需 FFmpeg，工具运行只需 Mutagen。NAS 首轮按一个合集预览和应用，再由用户检查 MA 专辑页。
