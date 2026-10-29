# 宽基趋势观察：实施计划草案

状态：planning；不是开始执行的授权。先完成任务材料评审，再按Trellis执行task.py start。

## 0. 规划收敛

- [x] 确认周报默认模型、消息接收目标和时间，完成PRD收敛。
- [x] 读取新服务接入、前端图表、代码复用、指数代码、调度生命周期和Windows测试规范。
- [x] 确认新应用端口、后端仓库形态及Trellis新package注册方式；不沿用无关默认package。
- [x] 根据实际代码核对复用入口；design.md中建议方案改为最终合同。
- [x] 用户评审后才task.py start；当前保持planning。

## 1. 独立计算与数据

- [x] 建立正式后端目录、依赖与测试配置；提取纯回归函数及类型。
- [x] 用固定fixture验证四组历史结果和当前两模型，不导入study目录的脚本或临时依赖。
- [x] 实现月线/日线数据适配、完整月判定、连续性和行情新鲜度校验。
- [x] 实现模型种类与不可变版本、当前位置、异常状态；dataZoom不触发计算。
- [x] 实现快照缓存、原子发布和失败回退，保留真实数据日期。

## 2. API与报告

- [x] 按项目代理口径提供history/chart/status及模型元数据接口。
- [x] 增加独立report-settings和报告历史，页面选择不写入报告配置。
- [x] 验证cache key、模型ID、数据截至时间跨层一致。

## 3. 前端两个Tab

- [x] 新应用复用现有页面风格与入口；实现历史5图切换。
- [x] 实现当前近10年/成立以来切换、区域摘要、轨道和模型区间。
- [x] 月K、三轨、拟合竖线、观察底色、未来虚线和tooltip单位正确。
- [x] 明确全历史全样本拟合文案；当前延伸文案不伪装目标价。
- [x] 处理375px/1440px、懒加载、resize、日期和数据异常状态。

## 4. 每周消息

- [x] 沿用现有调度模式，建立刷新/报告/发送状态和持久化去重。
- [x] 周五休市、整周休市、行情过期、月度模型切换、失败重试覆盖测试。
- [x] 用fake notifier测试，不发真实消息；确认目标配置后再验收真实投递。
- [x] 关闭与重启时无重复任务、无伪成功；保留模型与报告审计。

## 5. 接入、检查与交付

- [x] 落位Nginx upstream/location、NAS Compose服务与卷、入口导航、部署脚本全部映射、开发启动脚本、文档及gitignore。
- [x] 后端：在新包目录运行`uv run python -m pytest tests/ -v`，采用仓库Windows basetemp规范；覆盖AC1—AC5、AC7。
- [x] 前端：在新包目录运行`pnpm exec tsc --noEmit`、`pnpm build`；lint按该包实际配置执行，不能把未配置lint说成通过。
- [x] 浏览器验证Tab/历史/模型切换、刷新返回、缩放不重拟合、375px/1440px；覆盖AC6。
- [x] 根目录运行`docker compose -f docker-compose.nas.yml config --quiet`、`bash -n scripts/deploy-nas.sh`，验证生产API与静态资源路由；覆盖AC8。
- [x] 按项目check/update-spec/commit流程完成全范围验收；实际部署和启用消息按用户后续授权执行。

## 回滚范围

新增应用和服务的接线应可单独禁用，既有服务保持不变。关闭index-trends调度和通知即可停止新消息；不删除其他卷。模型版本与历史报告数据保留。


## 执行记录（2026-10-29）

- 后端 backend/index-trends：纯 Python 回归（lrc-ltb-port-v1）、SQLite 存储、APScheduler 周报（周五19:00 + 每日16:30 刷新）、50 个脱网测试全过；四窗口+两模型系数与 fixture 基准一致（rel=1e-9）。
- 前端 apps/index-trends：两 Tab + ECharts 月K通道图，URL 状态 tab/window/model；tsc 与 build 通过，375px/桌面浏览器实测通过。
- 接入 9 点全部落位（nginx/compose/deploy-nas/启动脚本/CLAUDE.md/DOCKER_DEPLOY/首页卡片/gitignore/launch.json）；compose config 与 bash -n 通过。
- 周报开放决定按 PRD 建议值落地：默认模型近10年、周五19:00、趋势延伸12个月；钉钉渠道未配置时报告存 no_channel 不发送。
- 遗留：真实钉钉投递需在 NAS .env 配 INDEX_TRENDS_DINGTALK_WEBHOOK_URL 后手动触发验证；nginx -t 需 Docker 引擎运行后执行（本机未启动 Docker Desktop）。

## 蜡烛图修复复验（2026-10-29）

- category 轴 K 线输入去掉月份序号，使用 [open, close, low, high]；保留未来月份 '-' 占位。
- candleData.test.ts 三项测试通过，包含 ECharts SVG SSR 实际解析 OHLC 与空月份渲染回归。
- 本机直接运行已安装的 TypeScript/Next CLI：类型检查和生产构建通过（pnpm 包装命令触发依赖重装提示，未重装依赖）。
- 生产构建本机 3011 预览：历史窗口1、当前近10年及成立以来切换通过，蜡烛实体与影线正常；375px 页面 scrollWidth/clientWidth 均为375，控制台无 error/warn。
- 真实钉钉投递和 NAS nginx 检查仍属部署验收，不在本次图表修复范围。
