# Playlist MA sync Implementation Plan

**Goal:** 生成设备清单时补齐所选合集标签并自动更新 MA，页面反映实际就绪状态。
**Architecture:** collection_metadata 处理音频；DeviceCollections 编排和持久化状态；MusicAssistant 同步与精确路径校验；前端展示状态。
**Tech Stack:** Python/FastAPI/SQLite/Mutagen、现有MA JSON-RPC、Next.js/TypeScript。
**Execution:** 先审阅本任务三份文档，再 task.py start；不覆盖其他未提交改动。

## Files
- 新增 src/collection_metadata.py、tests/test_collection_metadata.py：编号推导、补缺失、幂等、安全发布与审计。
- 修改 src/device_collections.py、tests/test_device_collections.py：兼容迁移、阶段状态、token保护、manifest更新、并发及旧接口保持。
- 修改 src/music_assistant.py、tests/test_music_assistant.py：来源发现、同步任务等待、错误脱敏、精确路径就绪验证。
- 修改 app/device-playlist.tsx，必要时新增状态组件及对应测试：全过程轮询与独立成功/失败状态；避开并行page.tsx/globals.css。
- 更新 docs/哆咪音频管理-功能说明.md 和相关spec：按钮的新行为、无备份规则、排障方式。

## Checklist
- [x] 读取 trellis-before-dev、适用音频/设备清单/曲目管理spec；记录当前未提交文件基线。
- [x] 先写MP3/M4A无标签生成回归、重复生成manifest不漂移、未选不改、冲突/无编号/损坏保护测试，确认新行为未实现。
- [x] 实现仅生成阶段的补标签服务，使用真实音频夹具确认不转码、原有标签保留、失败不发布半文件。
- [x] 为数据库迁移、token条件写入、下载/删曲/确认并发添加失败测试，再实现编排与状态。
- [x] MA模拟测试来源筛选、sync参数、任务pending→success/failed/cancelled/timeout、认证脱敏、路径不匹配/同名不同目录不得ready；再实现适配。
- [x] 增加前端状态/轮询测试，再实现文案，验证旧generation响应兼容。
- [x] 在 backend/kids-catalog 运行 .venv/Scripts/python.exe -m pytest tests -q，basetemp在项目盘；在 apps/kids-catalog 执行类型检查与npm run build。
- [x] 进行独立代码审查，重点检查补标签和完成台账的竞态、旧worker写入和MA假成功；修复后复验。
- [ ] 输出差异清单，排除曲目管理和housing-map的既有改动；用户授权后按范围提交/推送/部署。
- [ ] NAS 部署后由正常生成API选择当前合集，读取标签、完成台账、设备快照和MA精确文件归属；验证再次生成不需要人工确认。

## Rollback
保留旧镜像和生成数据库快照；回退仅kids后端/前端。不得批量删除音频、回滚用户删曲或覆盖原有标签。
