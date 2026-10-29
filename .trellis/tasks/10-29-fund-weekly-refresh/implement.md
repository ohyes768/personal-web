# 实施与验证

- [x] 新要求测试先红：旧单任务不满足四项时间/隔离/迁移。
- [x] 四项配置、per-job状态、共享队列、单tab采集、历史及设置兼容。
- [x] 右侧齿轮、原生dialog、四项管理和旧URL兼容。
- [x] `pytest tests/test_scheduler_management.py tests/test_weekly_refresh.py tests/test_market_full_pipeline.py tests/test_api.py -q --basetemp=.pytest-tmp-four-all`：64 passed。
- [x] `ruff check src/scheduler tests/test_weekly_refresh.py tests/test_scheduler_management.py`。
- [x] `node node_modules/typescript/bin/tsc --noEmit --incremental false`。
- [x] Playwright桌面/手机交互与截图，修复关闭焦点恢复及原生dialog居中尺寸；最终验证通过。
- [x] 更新后端契约；git差异检查；关闭临时浏览器与预览。

本轮变更尚未提交、未部署；并行任务目录保持原样。
