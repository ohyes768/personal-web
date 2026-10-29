# 基金四个 tab 每周自动刷新

## Goal

四个基金 tab 每周自动更新，避免依赖手动刷新。用户已批准推荐方案。

## Requirements

- 替换原每日调度，每周六北京时间 07:05 顺序刷新四个 tab。
- 市场预筛沿用页面默认：债基收益 10%、股基 20%；规模 5 亿、经理从业 5 年。
- 单项失败继续后续，保存各项执行结果；不部署。
- 用户追加批准管理页面：共用顶部入口，查看下次/上次执行、启用/暂停、立即执行及四项历史明细；暂停状态重启后保留。
- 立即执行与定时执行共用互斥，重复触发返回冲突；页面显示运行中并自动更新，清晰呈现加载、失败和空历史。

## Acceptance Criteria

- [x] 仅一个每周任务，Asia/Shanghai 时区，防止同一任务并发重入。
- [x] 四项参数、顺序、失败隔离、部分失败归类与持久化历史通过离线测试。
- [x] 阻塞采集在线程中执行，既有刷新/API 测试无回归。
- [x] 管理页入口、状态/时间、持久化启停、立即执行、运行进度和最近20次四项历史可用。
- [x] GET/PATCH/POST 代理透传通过模拟后端验证；桌面与390px手机交互、错误重试、失败启停不改状态、暂停后手动执行、运行中禁止连点及历史展开通过浏览器验证。

## 验证记录

### 管理页扩展验证

- `pytest tests/test_scheduler_management.py tests/test_weekly_refresh.py tests/test_market_full_pipeline.py tests/test_api.py -q --basetemp=.pytest-tmp-management-final2`：64 passed（沙箱外运行，绕过 Windows 事件循环沙箱挂起）。
- 前端 `tsc --noEmit --incremental false`、相关 Python 文件 Ruff、`git diff --check` 通过。
- Playwright 两批验证：1440px/390px截图、加载错误重试、启停失败保留状态、暂停后手动执行、运行中防重复、四项历史展开、基金共用 header 入口与空历史。仅 mock 采集接口，未跑真实全量刷新。
- Next 代理对本地回显后端验证 GET/PATCH/POST、路径/query/body/status 透传。
- `next build` 编译、类型检查、9页静态生成成功；standalone 文件追踪打包因 Windows 缺少 symlink 权限报 EPERM，完整生产打包未通过。本地独立缓存预览验证通过；尚未部署或提交。

- `pytest tests/test_weekly_refresh.py tests/test_market_full_pipeline.py tests/test_api.py -q --basetemp=.pytest-tmp-final-selector`：57 passed。
- 新增 11 项周任务测试；市场流水线测试冻结 fixture 对应日期，修正 L0 内部 import 的 mock 路径，避免真实网络。
- Windows 沙箱 Proactor 初始化在重复验证时挂起；无 socket IO 的线程测试使用 SelectorEventLoop 后全量通过。生产事件循环不变。
- 改动 Python 文件 ruff 和 git diff --check 通过。未提交、未部署；任务保留以便后续提交。

