# task-web 开发交接

日期：2026-11-05（Asia/Shanghai）
状态：需求交接，尚未创建 Trellis 任务，尚未实现或部署。

## 用户已确定的方向

在 personal-web 中新增 task-web，用 Web 页面管理 Ubuntu NAS 上的定时任务，方便排查有没有执行、何时执行以及为什么失败。

- 不使用 n8n。
- 普通 Shell/Python 任务直接由程序调度执行，不需要 AI agent 或模型 token。
- 第一版聚焦定时、任务管理、执行记录和日志，不做通用可视化工作流平台。
- 后续在 personal-web 的开发会话中创建 Trellis 任务、完善设计并实现；本次只建立项目入口和交接文档。

用户原话：

> 不用 n8n 了，就只需要定时任务，然后管理，方便排查是否执行的功能
> personal-web 建个 task-web 项目吧！建个handsoff 文档！后续那边去开trellis任务进行管理

## 项目位置与开发起点

当前入口：apps/task-web/HANDOFF.md。
建议遵循仓库现有布局：前端 apps/task-web/，后端 backend/task-web/。后端目录、代码和依赖尚未创建。

仓库现有模块包括 skill-manager、rss-relay、fund-select 等，前后端通常分开部署。README 的模块计数与实际目录不完全一致，后续以实际代码、部署文件和 Trellis specs 为准。

开始开发时：

1. 阅读根 AGENTS.md、.trellis/workflow.md，按 personal-web 的流程创建 task-web Trellis 任务。
2. 读取受影响包的 .trellis/spec/，确认新增模块、权限、导航、API 和部署约定。
3. 查看 apps/skill-manager 与 backend/skill-manager 等模块，判断可复用的布局与后端模式；不要假定已有统一登录或调度服务。
4. 将本交接中的已确定需求写入 PRD，把待决策内容留在设计中，不将建议误当用户已批准的技术方案。
5. 核实 NAS 实际部署、既有调度来源、执行账号与 Python 环境，再规划迁移。

## 第一版功能范围

### 任务管理

- 新建、修改任务：名称、说明、命令及参数、工作目录、cron 时间表达式、时区、超时、启停状态。
- 显示上次执行时间、上次结果和下次计划时间。
- 支持手动立即执行；明确记录触发来源是定时还是手动。
- 暂停任务只阻止后续自动触发，不默认终止正在运行的进程。
- 删除任务与历史记录的关系在设计中明确，避免无意丢失排查证据。

### 执行记录与日志

- 每次运行有独立 run_id，记录 task_id、计划时间、实际开始时间、结束时间、耗时、触发来源、状态及退出码。
- 区分等待、运行中、成功、失败、超时、中断；互斥导致跳过时也需要留记录及原因。
- 保存 stdout/stderr，执行过程中可查看持续产生的日志，结束后仍可回看。
- 列表按任务、状态和时间筛选。
- 到时间却没有运行不能与成功混淆；记录调度心跳和应执行时间，提供漏执行或调度离线的识别依据。具体检测方式在设计阶段确定。

### 最小可靠性

- 同一任务默认不并发运行，手动与定时触发共用互斥机制。
- 超时应处理整个任务进程组，避免只杀 Shell 留下 Python 子进程。
- 服务重启后不能把旧运行永久保留为运行中，应标记中断或核验实际进程。
- 调度只由一个有效调度实例负责，避免多 worker/多副本导致重复执行。
- 明确停机期间漏掉的计划是否补跑；通知任务不宜未经配置集中补发。默认策略需写进 PRD/设计。
- 日志轮转或按期限清理，保留策略可配置，避免无限增长。
- 命令以指定执行账号、工作目录和环境运行；不要把含密钥的环境变量原样返回页面或写入日志。

## 成功判定的边界

程序退出码为 0，只能证明该进程按其约定正常退出，不一定代表钉钉已收到消息。

接入每个脚本前应检查：

- 获取失败、空数据、推送失败分别返回什么退出码。
- 空批次是正常跳过还是异常，页面上如何呈现。
- 是否把异常捕获后打印日志却仍返回 0。
- 是否启动后台子进程：例如 daily_pick.py 会继续启动 Hermes worker，父进程成功不能代表 AI 分析和后续投递完成。

第一版可先展示进程级结果；页面应明确结果含义。若希望显示投递成功，需脚本输出结构化业务结果或回执，不靠匹配一条“成功”日志来推断。

## 建议实现思路（尚未最终选型）

- Web 前端沿用 personal-web 的现有技术和组件规范。
- Python 后端提供任务、运行记录、日志 API；SQLite 保存元数据与运行历史，日志文件单独保存。
- 使用成熟的定时调度组件，不手写 cron 表达式解析与调度算法。
- 调度/执行进程独立于前端请求生命周期，Web API 重启、刷新页面不应中断任务或重复注册计划。
- NAS 原生执行与容器执行必须先选定：宿主机现有路径、Python 依赖和用户权限不能直接假定在容器内可用。
- 默认只接入预先登记的任务；谁能新增/修改任意命令需要适配 personal-web 的权限体系。

第一版不包括：多机器执行器、任务依赖图、可视化编排、脚本在线 IDE、AI 自动分析日志、自动修复，以及替换所有 Hermes 定时任务。

自动重试也不应直接套到所有推送任务：失败可能发生在消息已发出但回执未记录之后，须先验证幂等性。

## 已检查的 NAS 信息

服务器：n100-nas，用户 ohyes768。
业务仓库：/home/ohyes768/stock-info-dingding。
NAS 有 /usr/bin/crontab，cron 服务运行中；systemd 版本为 255。

仓库 hooks.json 是一个包含 17 项的列表，但不是系统 crontab。当前 xwlb_n8n_webhook.py 是业务执行脚本，并非通用调度服务。尚未定位全部任务当前由谁定时触发，不要仅根据文件名推断实际运行架构。

已看到的 hook ID：

- gold-push、fund-push、sector-push
- a-stock-push、hk-stock-push、natgeo-push
- rss-meiritou-gu、rss-zi-xun、rss-li-cai
- git-pull、xwlb-push、xwlb-rss-push
- damai-push、damai-sz-push
- star50-macd-push、daily-pick-push、etf-rotation-push

hooks.json 可用作任务登记来源参考，但不能假定它包含 cron 时间或启停信息。

不要在交接文档、仓库或前端写入真实 webhook token、签名密钥、模型密钥或 .env 内容。

## 可优先接入的普通程序任务

| 功能 | 相对 stock-info-dingding 的入口 | 备注 |
|---|---|---|
| A 股新股通知 | a_stock_push.py / run_a_stock.sh | 推荐首个接入任务 |
| 港股新股通知 | hk_stock_push.py / run_hk_stock.sh | 抓取及模板推送 |
| 板块涨跌通知 | dingtalk_em_api.py / run_sector.sh | 东方财富数据、排序与映射 |
| ETF 双动量轮动 | etf_rotation_push.py / run_etf_rotation.sh | SMA20、20 日动量及固定规则 |
| 科创50 MACD | star50_macd_push.py / run_star50_macd.sh | 固定指标规则 |
| 基金 M120 偏离度 | fund_m120_push.py / run_fund.sh | 固定指标规则 |
| 大麦活动 | damai/damai_spider.py / run_damai.sh、run_damai_sz.sh | 活动与票档采集 |
| RSS 转发 | rss/push.py / run_rss.sh | 标签、去重与推送 |
| 新闻联播转 RSS | xwlb_to_rss.py / run_xwlb_to_rss.sh | 转发已有摘要；上游生成另算 |

这些任务的实际启用状态与计划时间尚未核实。

A 股新股现有启动脚本已确认：

```bash
#!/bin/bash
cd /home/ohyes768/stock-info-dingding
export PUSH_MODE=1
exec /usr/local/bin/python3 a_stock_push.py
```

立即执行会真实推送。开发验收优先使用无外发测试任务，再验证显式 dry-run，最后才在确认接入后启用正式计划。

以下功能不应被错误标为全程不需要 AI：

- daily_pick.py：选股及材料通知是程序逻辑，后续 Hermes 深度分析需要模型。
- gold_price_push.py：当前会调用 DeepSeek，分析失败会中止推送。
- natgeo/natgeo_push.py：中文翻译调用 DeepSeek，无密钥可跳过翻译。
- 新闻板块影响分析：有 LLM 分支，关键词模式可关闭 LLM，但结果不同。

## 迁移和验证建议

1. 先完成任务清单调查：系统 cron、systemd timer、webhook、Hermes/OpenClaw 等可能同时存在；只迁移本次选定任务。
2. 用不会外发的成功、失败、长时间运行和超时脚本验证记录、日志与互斥。
3. 验证重启后的状态恢复、漏执行识别、时区和下次运行时间。
4. 首个正式接入选择 A 股新股通知，核对其进程退出码与业务结果。
5. 导入时默认禁用新计划，确认旧入口停用后再启用；避免两个调度器同时发送。
6. 每个任务保留旧计划记录和回滚办法，确认运行记录与业务投递结果一致后再扩展其他任务。

## 当前完成与未完成

已完成：明确最小需求、查看 NAS 脚本和 hooks 结构、建立本交接入口。

未完成：Trellis 任务、最终技术设计、前后端脚手架、任务 CRUD、调度器、数据库、执行器、日志页面、部署和迁移。

本轮未修改既有 NAS 调度，未新增计划任务，未发送测试通知，未提交或推送 personal-web 仓库。