# 实施计划

使用已批准 PRD 与 design.md，在当前工作区执行；用户已明确“开干”。

- [x] 新增 tests/test_device_collections.py：真实音频 fixture，覆盖计数、同数稳定、5 首插队、完成记录独立、失败保留、旧版本拒绝、并发及容量限制；先运行确认缺失功能导致失败。
- [x] 新增 src/device_collections.py 与 src/music_assistant.py：SQLite 当前快照/完成清单、扫描和 MA 只读精确映射。
- [x] main.py 接入下载状态与完成清单、后台生成及只读接口，兼容既有下载测试。
- [x] 页面新增生成操作与真实编号清单，错误和跳过原因可见；compose 增加 MA 配置，docs 记录设置与设备/HA 契约。
- [x] 在 backend/kids-catalog 执行 .venv/Scripts/python -m pytest -q；在 apps/kids-catalog 执行 pnpm exec tsc --noEmit 和 pnpm build。
- [x] 按 trellis-check 复核接口流、事务、凭据与文件变化；记录真实 NAS/MA 凭据阻碍，不以 mock 代替现场验收。
- [x] 更新开发契约与验证记录，不自动提交或部署。

- [ ] 配置真实 MA token 后验证 NAS 专辑匹配与播放，完成 ESP32/HA 协作联调；当前未部署。
