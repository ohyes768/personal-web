# 价格时效与采集设计

## 数据边界

新增 price_policy.py 统一上海日期、6个月月差与30天陈旧判断、双价投影。data_loader 继续返回兼容 price/price_type/date（有效签约优先），新增 deal/listing/history_deal/counts 与 refresh 字段。每条价格包含所属月份、采集日、来源 URL、stale。过期签约仅进入 history_deal；无有效价仍可返回历史/套数，兼容 price=null。合并来源按价格类型分别选最新，不按文件顺序覆盖。新房 API 一律隔离二手价格。租售比只使用兼容有效 price，日期优先价格所属月份。

套数附独立采集时间；抓到首页但没有价格仍生成 counts 快照，不冒充价格。采集器不再把走势图长度当成交样本数，保存 trend_point_count；不暴露固定置信度为测量值。

## 采集范围与任务

资格来源复用 community_views 的有效 admission_state，不依赖是否已上地图（缺轮廓仍可采）。要求覆盖内坐标、真实小区、有效 matched TMSF community 来源，排除 new_house/project。无台账不猜测已收录，返回空计划。每个小区所有有效 community 来源按来源去重采集；UI/统计按主小区去重。每个请求前及返回后重查资格与绑定；撤销或换绑结果不落盘。定时默认 all；POST refresh 增 mode=all|missing，GET 增 eligible/missing。

补齐只选择没有有效 deal/listing 的已收录小区，不因缺一类型而重爬。启动时重新计算；空集合409，不产生任务。旧 limit 参数保留。所有入口共用 running 互斥。

每轮报告 outcomes（按来源收集，按小区汇总）与 updated/noData/failed/skipped，四项互斥并合计total；retained 为保留原价格的小区数，可与前三类重叠。请求部分页失败即标记 partial，不吞 errors。正常无价与过期价分别记录原因。每小区刷新结果持久化到 price_refresh_status.json，页面重启后仍可看旧价保留原因；套数或价格未成功获取不更新其采集时间。任务取消不发布快照，仅记录取消尝试；主快照原子替换后不允许描述为未改动。

## 发布与兼容

价格 JSONL 是权威，CSV 是可重建导出。临时文件在目标目录、flush/fsync 后 os.replace；清理临时文件。主快照失败保留旧数据；CSV/状态导出失败报告警告并说明主快照已发布。无新记录不改主快照，仍保存刷新结果。保留旧键、旧字段；失效价格仅从当前投影移除，原始历史不删除。

## 界面

沿用现有样式与紧凑布局。提取 PriceDetails/PriceRefreshControls，便于真实 SSR 验证。两个按钮“刷新已收录”“补齐价格（N）”；运行时显示进度/停止，终态显示有效更新/无数据/失败/保留旧价和警告。挂/签各展示时间及陈旧提示，过期成交在历史参考区；看板同样展示双价及状态。页面加载即查询任务，覆盖定时启动和重新打开页面。

## 回滚

无需离线数据库迁移。新增 JSON 字段与状态文件兼容旧读取；可回滚代码并用启动前备份恢复主快照。不得在线上执行迁移或真实爬取验证。
