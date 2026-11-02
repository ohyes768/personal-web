# 当前实现与只读研究

核验日期：2026-11-02。本轮没有修改业务代码、安装依赖、触发刷新或发送消息。

## 代码依据

- backend/index-trends/src/data/provider.py：腾讯fqkline适配器，返回行顺序为日期/开/收/高/低；现有主调用month和day。
- backend/index-trends/src/services/trend_service.py:93：refresh_sync先写月K和日线，再计算模型，最后写元数据；周线实施需要改为校验计算后一次事务发布。
- backend/index-trends/src/services/trend_service.py:129：固定120月/36月步进、近120完整月、成立以来；不能仅把period换成week。
- backend/index-trends/src/services/trend_service.py:168：build_chart按月坐标生成拟合和延伸序列；240行current_status按月投影；284行data_status按月新鲜度判断，需同步换周。
- backend/index-trends/src/core/regression.py：OLS使用enumerate；deviation是前移一根K线的公开移植公式，不是标准残差RMSE。周线保留该特性但显式使用自然周x并升级版本。
- backend/index-trends/src/services/store.py:20：月K表；42行models带months/data_cutoff_month；187行latest_model按月截止排序。不能复用这些月字段储存周值。
- backend/index-trends/src/services/report_service.py:52：周报已先刷新，再生成发送；78行仅凭日线缺失判断整周无交易，不能直接沿用到强调可靠性的周线方案；131行投影仍按月；211行上周比较未隔离周期。
- backend/index-trends/src/services/store.py:258：upsert_report可覆盖同幂等键非sent报告，新周期替换前须保留原文审计。
- apps/index-trends/lib/types.ts及components/TrendChart.tsx：API镜像和图形大量使用months/month/fit_boundary_month，需要联合迁移。
- apps/index-trends/package.json：仅dev/build/start，无lint及test脚本。现有candleData.test.ts含ECharts SSR回归。
- 既有任务：.trellis/tasks/archive/2026-10/10-29-index-trends/。该任务开发验收完成，但规划中的部分旧状态文案未清理，不能据“planning”旧标题判断当前代码未实现。

## 线上只读核验

NAS docker ps显示index-trends-backend健康、frontend及nginx运行。读取GET status与reports，没有POST或改变配置：

- 收盘2026-10-30：3985.50；成功抓取时间2026-10-30 19:00，模型截至2026-09。
- 近10年月模型2016-10—2026-09：位置32.19%；下/中/上轨3308.4301 / 4360.0793 / 5411.7284。
- 成立以来月模型2005-04—2026-09：位置32.06%；下/中/上轨2960.3342 / 4559.2229 / 6158.1117。
- 周报2026-W44，business_status=normal，status=no_channel，error=channel_not_configured，sent_at=null。

这些数字是迁移前基线，不是周线计算结果，也不能标为11月2日收盘。

## 周数据可用性

在既有容器中以urllib只读请求腾讯接口参数sh000300,week,,,1600,qfq，响应code=0、1102条：首条2005-04-08，末条2026-11-02。只能证明接口能给历史周K，尚未逐周验证历史连续性、日历匹配、所有OHLC或回归数值。

末条是进行中周，验证“供应商返回了记录”不等于“周已完成”。后续实现必须保存固定fixture并核验完整性，不能把本次探测当成验收通过。

## 交易日历选择

仓库dividend-select和macro用akshare交易日历模式，但其失败后默认当作交易日的降级不适用本任务。为避免跨包导入与额外网络爬取，规划采用独立XSHG适配层，依赖exchange_calendars（带pandas/numpy，包体增加属已知代价）。

上游依据：[exchange_calendars发布记录](https://github.com/gerrymanoim/exchange_calendars/releases)包含4.12的2026年XSHG修复；[预计算日历边界实现](https://github.com/gerrymanoim/exchange_calendars/blob/master/exchange_calendars/precomputed_exchange_calendar.py)明确按已记录年份约束范围。实施前需要验证实际锁定版本覆盖全训练区间与当前周；越界须异常，不可凭工作日猜测。上游选择已完成研究，本轮没有安装依赖或验证本地日历会话数。

## 范围和限制

用户最终只要求Trellis规划。任务保持planning，没有启动实现、运行测试、部署或真实推送。现有未提交住房改动属于其他工作，保持原样。
