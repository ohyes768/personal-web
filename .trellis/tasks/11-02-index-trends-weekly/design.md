# 周线模型与周报技术设计

状态：planning。需求来源为prd.md；2026-11-02用户将本轮范围收敛为仅规划。

## 1. 方案与边界

采用历史、当前和周报统一周线；不采用“仅把图改成周K仍用月模型”，也不增加月/周双周期界面。继续使用现有FastAPI、SQLite、ECharts及单实例APScheduler，不增加服务、端口或独立数据库文件。

后端范围为backend/index-trends，前端为apps/index-trends。当前Trellis尚未注册这两个package，task.json的package必须为null，meta记录实际路径，不能继承默认douyin-processor。

## 2. 周数据和交易日历

- 周主键week_start使用周一YYYY-MM-DD，week_end为其后第6天，iso_week由isocalendar产生。行情date是实际交易日，不能拿供应商date当作自然周结束日期。
- provider沿用腾讯fetch_kline，增加week周期，申请1600条；返回不足以覆盖2005-04、重复周、乱序、非有限价格及OHLC错误均拒绝发布。另取近期日线用于最新已完成日定位与周末收盘交叉校验。
- 新增独立trading_calendar适配器，封装可注入的sessions(start,end)，脱网测试用显式会话集，避免测试受系统日期或在线日历变化影响。
- 日历实现采用pandas_market_calendars的SSE日历（依赖约束>=5.1,<6，实施时锁定通过验证的版本），并以exchange_calendars的XSHG会话表做交叉验证。2026-11-02实测证据：exchange_calendars 4.7—4.13的XSHG首会话均为2006-11-02，无法覆盖"成立以来"起点2005-04；pandas_market_calendars的SSE覆盖2005-04-01起、2005-04有21个交易日。两源在重叠区间2006-11-02至2026-12-31的4902个交易日逐日比对完全一致、零差异，故SSE日历可用且无需拼接两个日历。
- 该日历有年份上界，禁止越界退回“周一到周五皆交易日”。初始化显式覆盖2005-04-01至当前周日，若超出库支持范围则返回calendar_unavailable，旧快照继续可读但标为异常。2027年前须验证依赖日历覆盖并升级锁文件。
- 一周有会话且最后会话日15:05已过才完整；未来周及当前未完成周不进入训练。日历确认整周无会话时没有周K；有会话却缺条目、或最后交易日不匹配，判为missing_data。
- 2005年首周只使用指数发布后的部分周，明确标记，不要求发布前行情。完整历史按日历逐周验证，不能只检查相邻数据间隔。
- 最新日线必须覆盖当前时刻最近应已收盘的会话日；周报周K收盘与当周最后交易日日线须一致（允许0.01点显示精度误差），否则异常。校验失败不更新成功抓取时间和已发布截止周。

## 3. 训练区间和回归坐标

每个样本x=(week_start-origin_week_start).days/7，y=周收盘。OLS使用显式x；整周休市会留下x间隔，不能使用enumerate(closes)压缩掉时间。沿用deviation=sqrt(mean((y-(a+b*(x+1)))^2))，其中+1表示一个自然周；宽度仍为2×deviation。另设算法版本lrc-ltb-week-v1，不更改旧月线算法及基准。

周归属按week_end落入日历区间：

- 近10年：截止完整周的week_end次日为end_exclusive，从该日期减10个日历年得到start_inclusive；取start_inclusive <= week_end < end_exclusive的完整、有交易周。若遇2月29日采用目标年2月最后一天。窗口头尾和实际样本周数在响应中分别声明。
- 成立以来：从包含2005-04-08发布周的首条有效周K起，到最近完整、有交易周。
- 固定窗口：名义区间仍为[2005-04-01,2015-04-01)、[2008-04-01,2018-04-01)、[2011-04-01,2021-04-01)、[2014-04-01,2024-04-01)，后续每3个日历年增加。周的week_end在区间内才参与训练；区间结束边界尚未到达时不提前发布完整窗口。观察期为名义end_exclusive起3个日历年，最多展示已有完整数据，样本外数据不参与拟合。
- 当前图未来延伸52个自然周，描述为“约1年”；历史观察仍用3个日历年，不机械替成156条有交易周。

固定窗口ID继续采用fixed-YYYY-MM作为页面稳定选项；实际模型ID为新的周线标识，旧链接能恢复同名时间窗口，但显示周线口径。哈希必须包含样本周坐标和收盘，不能只散列收盘序列。

## 4. 存储、发布和兼容

保留monthly_bars、models和原data_meta作为旧月线档案；新增weekly_bars、weekly_models、weekly_data_meta与schema_migrations。weekly_models明确保存sample_count、timeframe=week、calendar_window_start/end、fit_start/end、data_cutoff_week、算法版本和训练哈希，不复用months字段装周数。

新模型kind：historical_fixed_10y_weekly、trailing_10y_weekly、since_inception_weekly。模型ID至少包含指数、week周期、kind、拟合周起止、算法版本、坐标和价格哈希。全历史与当前成立以来复用同一个模型。

一次刷新在内存完成取数、校验、所有模型计算，再以一个SQLite事务发布周K、日线、模型和元数据；失败回滚，保留旧成功快照。模型记录按ID只插入不覆盖。读端在一致读事务中解析同一snapshot_id，当前摘要和图形同时带该标识；前端发现两次请求版本不一致时重新取同一模型ID，不混画。

report_settings在有版本的幂等迁移中将trailing_120m/since_inception映射为对应周线kind，保留enabled、channel及send_cron。旧reports行不重写，新增可空snapshot_json用于新周线报告不可变原始快照。继续使用指数|ISO周|weekly去重键；已sent的旧月线报告仍阻止同周自动重发。非sent旧报告保留原记录，在新报告生成前归档到report_attempts，避免覆盖原文。新尝试及其投递结果追加审计。

## 5. API和页面合同

保持外部/api/index-trends及现有端点，周响应使用明确新字段：

| 层级 | 字段 |
|---|---|
| model | timeframe:week、sample_count、calendar_window_start/end、fit_start/end（周一）、fit_last_trade_date、data_cutoff_week、model_id、coefficients |
| data_status | state:ok/stale/empty/error、data_cutoff_week、expected_cutoff_week、expected_close_date、daily_last_date、captured_at、reason、snapshot_id |
| chart bars | week_start、date（实际末交易日）、open/close/high/low、partial |
| channel series | weeks（所有自然周周一，含休市时间槽）、mid/upper/lower |
| chart | fit_boundary_week、extension_series、extend_note、snapshot_id |
| history window | stable_id、calendar_window_start/end、fit_start/end、observation_end_week、sample_count、model_id |
| status | projection_week、price_as_of、close、三轨、position_pct、region、model、data_status、snapshot_id |
| refresh | success、message、data_cutoff_week、weekly_count、new_models、snapshot_id |

不再把周值写进data_cutoff_month/months等月字段。旧URL model=trailing_120m/since_inception在前端映射到新模型并replace URL；API旧kind别名仅解析为周线并在响应明确timeframe，旧月线模型ID请求返回明确的旧周期不可用于周线图提示，避免把旧ID当不存在静默换图。

TrendChart用相同自然周坐标构建x轴，休市和未来无K线位置沿用字符串'-'；实线/虚线、观察区标注、隐藏Tab初始化与resize遵守现有ECharts契约。tooltip显示周范围和实际收盘日，当前周明确“进行中”。模型切换时清空旧摘要，日期和样本数一同更新。

## 6. 周报一致性与比较

周五19:00调度不变，保留每日16:30刷新和refresh_lock。报告先刷新，再锁定model_id、行情、日历和snapshot_id；所有正文与保存字段从这一份快照生成。当天15:05前手动触发不得把当周未完成数据写为正常最终周报并占用正常去重投递机会。

周涨跌=本周末收盘/最近上一有交易周末收盘-1，跨整周休市时明确比较基期实际日期。没有可比基期则显示不可比较。

对同一周线kind的上周快照，将总位置变化拆成：价格影响=p(本周价格,上周模型投影到本周)-p(上周价格,上周模型投影到本周)；模型影响=p(本周价格,本周模型)-p(本周价格,上周模型投影到本周)。另列时间推进影响=p(上周价格,上周模型投影到本周)-p(上周价格,上周模型在上周)。三项之和须等于新旧快照位置之差；不能把每周重拟合后的位置变化全称为价格变化。缺少旧快照系数、跨月/周周期、旧快照异常时只展示当前值及不可比较原因。

business_status正常/休市/数据异常与投递status分离；缺模型也必须是异常业务状态，不能只在正文写不可用而保存normal。钉钉无配置仍no_channel，不增加新渠道、不填入密钥。本任务不配置或验收真实投递。

## 7. 回滚和实施门槛

部署前备份SQLite，用其副本验证迁移与重复迁移；不能在旧容器运行期间恢复数据库文件。回滚需停新服务、恢复旧镜像与备份数据库，再启动旧服务；保留新的备份和投递审计以核对去重，不删除卷。前后端需成套上线，避免周API与月字段页面混跑。

本轮只规划，不运行依赖安装、测试服务、迁移、task.py start或部署。后续获得实施授权后先核验日历覆盖、历史周K完整性与固定fixture，再按implement.md执行。
