# 验证记录（2026-10-19）

## 结果
- Windows：`backend/kids-catalog/.venv/Scripts/python.exe -m pytest tests -q`，最终 64 passed, 1 skipped。跳过真实 symlink 权限用例；现有 Starlette/httpx 废弃提示 1 条。
- WSL Ubuntu Python 3.14：`python3 -m pytest tests/test_audio_tags.py --basetemp=.pytest-tmp-linux -o addopts= -q`，19 passed, 2 skipped。两项压缩音频包测试因 Linux 无 FFmpeg 跳过，Windows 对应 MP3/M4A 均通过；Linux symlink 用例通过。
- Linux 测试使用仅包含 Mutagen 的临时 PYTHONPATH，未共用 Windows venv 原生扩展或 pytest 临时目录。
- `uv lock --check --offline` 通过；CLI --help 通过；git diff --check 通过；Trellis task validate 通过。
- requesting-code-review 独立只读审查后修复了未编号文件艺术家统计、损坏文件重复曲序统计和备份目录 fsync，修正均有先红后绿回归测试。最后限定复核通过。

## 已覆盖
- 预览只读、中文 MP3/M4A 五字段补齐、非目标标签保留、重复运行幂等。
- 标签冲突、重号、损坏、无编号、单合集选择及路径越界处理。
- 完整备份、字节级恢复、重复恢复、备份损坏拒绝、后续人工编辑拒绝覆盖。
- 备份失败/原子替换失败/目录同步失败时不发布；过期预览不覆盖外部编辑。
- MP3/M4A 编码音频包 SHA256 不变（Windows FFmpeg）。

## 观察
一次中间全套回归触发原有 test_partial_download_reports_skipped_counts 的时序失败：测试只等待 queued，没有等待 running 结束。未改动下载器或该测试；最终完整回归通过。此观察不归因于标签工具。

## 边界
没有部署 NAS，没有批量修改真实音频，没有执行真实断电测试，没有验证 MA 重扫结果。Windows 没有 POSIX 目录 fsync 保证。无 commit/push，当前分支 feat/kids-existing-audio-tags 保留本地未提交改动。
