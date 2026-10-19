# 历史音频标签工具 Implementation Plan

> 执行方式：本会话顺序执行，不派生代理。用户已批准方案。未授权提交或部署。

**Goal:** 提供保守、可预览、可恢复的历史文件补标签命令。
**Architecture:** 扫描推导、事务文件操作、CLI 三个模块；Mutagen 读写；原始备份与 SHA256 恢复记录。
**Tech Stack:** Python 3.12+、Mutagen、pytest；测试夹具由 FFmpeg 生成。

- [x] 创建 tests/test_audio_tags.py 和短音频夹具：预览/中文标签/冲突/损坏/重复曲序/幂等/压缩音频包不变/恢复保护/原子失败。
- [x] 运行 python -m pytest tests/test_audio_tags.py --basetemp=.pytest-tmp，确认新行为尚未实现。
- [x] 新建 src/audio_tags.py、src/tag_files.py、src/tag_audio.py，支持预览、--apply、--restore、--album、--backup-dir。
- [x] 添加 mutagen 依赖及 uv.lock，pytest 临时目录落项目盘并忽略。
- [x] 运行新测试及现有 tests 全集；检查 CLI --help 和默认预览。
- [x] 新建 docs/已下载音频补标签.md：NAS 容器重建、单合集预览/应用、备份目录独立挂载、MA 刷新及恢复步骤。
- [x] 检查 git diff --check、改动范围和任务验证记录；不提交、不部署、不批改真实音频。
