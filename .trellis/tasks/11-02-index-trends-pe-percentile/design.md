# 理杏仁沪深300 PE分位设计

## 目标和边界

填补当前宽基页面和周报缺少估值分位的行为缺口。使用理杏仁提供的 PE-TTM 总市值加权近10年分位，不在本地重新计算排名。数据源、日期选择、状态判断和展示单位由后端统一；两个趋势模型共享估值，切换模型不改变估值口径。

只在当前通道摘要与周报增加估值信息，不修改趋势拟合、历史回溯图、通道位置、调度时间、投递幂等键或推送渠道。不增加估值历史图、窗口切换、估值交易信号或其他来源回退。

## 已核实的实现位置

- `src/config.py`：Pydantic Settings，环境变量统一 INDEX_TRENDS_ 前缀。
- `src/main.py`：构建 Store、WeeklyTrendService、ReportService；每日与每周任务在此组装。
- `src/api/routes.py`：/indices/{code}/status、/refresh、报告查询与任务触发。
- `src/services/trend_service.py`：WeeklyTrendService 持有 refresh_lock、交易日历与完整周状态。
- `src/services/store.py`：SQLite及schema_migrations；周报已有snapshot_json和report_attempts。
- `src/services/report_service.py`：周五19:00刷新后发送，已有已发送报告幂等检查。
- `apps/index-trends/components/CurrentTab.tsx`：当前通道摘要；lib/types.ts镜像API类型。
- `docker-compose.nas.yml`：现有服务environment需透传新增Token。

路径未写前缀时相对 backend/index-trends；完整前端路径如上。

## 供应商契约

POST https://open.lixinger.com/api/cn/index/fundamental

请求固定stockCodes=["000300"]，metricsList=["pe_ttm.mcw", "pe_ttm.y10.mcw.cvpos"]。使用显式startDate/endDate查询目标日前30个日历日到目标日的小范围，以便判断更新滞后；绝不依赖默认endDate（官方默认上周一）。只发送所需指标，无需回填10年日序列。

官方示例已确认：成功code=1；data为数组；stockCode为字符串；date是带+08:00时区的ISO时间；指标字段是平铺的带点号键，不是嵌套对象。cvpos原值为0–1比例，转为percentile_pct=原值*100。

新增 `src/data/lixinger.py`，复用httpx，通过依赖注入Client做离线测试。校验HTTP状态、业务code、指数代码、北京时间日期、目标日上界、字段存在性、finite数值及0<=cvpos<=1；PE必须为正数，拒绝bool、NaN、Infinity与缺省填零。独立挑选最新合格记录，不假设供应商排序，不接受未来记录。

单次请求总超时上限10秒；MVP不自动重试，避免权限错误和周报发送长时间等待。失败保留既有合格数据，不发布部分解析结果。错误对外用固定reason码和脱敏说明，禁止直接回显供应商正文、请求体、Token或异常中的敏感内容。

## 配置与凭据

新增 INDEX_TRENDS_LIXINGER_TOKEN，默认空，使用SecretStr或等效防repr泄露机制。仅后端读取，Compose透传，文档提供占位示例。未配置时仍启动成功；不加前端配置Token表单，不写入report_settings或API。账号开通、付费购买与真实Token配置由用户自行处理，实施和离线验证不依赖提供真实凭据。

## 日期语义

复用现有交易日历和完整周判断，以Asia/Shanghai为准：

1. 当前页面显示最近已结束的自然周内最后交易日的估值，进行中的周不取盘中或日频最新值。周五收盘完成后可显示本周。
2. 周报以报告所属自然周的最后交易日为目标，与正常周报close_date对齐；绝不能直接now减7天，否则周五周报会错位。
3. 全周休市时沿用既有休市报告分支，可附最近有交易完整周的估值，明确日期及休市沿用，不能标为本周新值。
4. 日历不可用时返回error/calendar_unavailable，不猜测周五为交易日。
5. 来源日期早于目标日时状态stale，可展示最新已有值但必须明确“未更新至目标日”；不得标为目标周新数据。
6. 来源无可用记录时返回empty；历史记录不取目标日之后的数据。MVP不开放历史估值查询API。

## 存储与状态

新增迁移003（遵循现有可重复执行方式），增加估值日表与单行采集状态表，独立于weekly_data_meta：

- index_valuations：复合主键(index_code, source, metric, window, date)；pe_ttm、percentile_ratio、captured_at。metric=pe_ttm_mcw，window=y10，source=lixinger。只存必要业务字段，无Token。
- valuation_fetch_meta：目标日期、最近尝试时间、最近成功时间、脱敏错误码。请求失败不覆盖历史成功值。

服务层新增 `src/services/valuation_service.py`，统一目标日解析、fetch/upsert和read状态。成功结果与抓取元数据在事务内发布；失败元数据单独更新。报告快照保留发送时的估值对象；后续来源修订可更新缓存，不回写已发报告。

对外统一valuation对象：state(ok/stale/empty/error/disabled)、reason、source、metric、window、target_date、as_of、pe_ttm、percentile_pct、captured_at。数值缺失用null，不用0。disabled表示无Token；error可伴缓存值，但必须显示“读取缓存/更新失败”，不能伪装ok。state=ok要求数据日期严格等于目标日且无本次采集错误。页面显示分位1位小数、PE2位小数；存储保留原精度。

## 调用与并发

- main.py注入同一个ValuationService给API与ReportService，不让估值供应商侵入趋势模型算法。
- status API只读本地缓存，添加valuation字段；不在GET内请求供应商。无趋势模型时仍可返回独立valuation字段。
- 每日任务和手动/refresh在原有行情刷新流程结束后尝试刷新估值，即使行情失败也尽可能独立采集；原有行情成功语义不被估值失败改为失败，响应可附估值状态。
- 每周报告在幂等/禁用/周未完成检查之后、生成正文之前获取目标日期估值；失败不改变原business_status和发送结果，只增加估值提示。
- 启动时复用生命周期任务做一次估值初始化；补发路径与周报共用服务，避免双请求。不创建新的调度器或持续重试任务。
- 写入沿用现有refresh_lock；相同目标日已有成功记录时跳过网络请求，失败重试至少间隔15分钟，日历目标日变化不受旧目标退避影响。已sent报告不因估值更新而重发。

## 页面与周报

当前通道摘要增加独立估值区域：`PE-TTM近10年分位 xx.x%`为主，PE倍数、数据日期、总市值加权和理杏仁来源为辅助文本。保持现有样式，375px无横向溢出。估值独立于通道百分比，不能复用其区域标签或把通道“低位”解读为估值低。

stale展示目标日期和实际截止日；disabled/empty/error用易懂文案。旧后端未提供valuation时显示暂不可用，不使主图报错。

周报增加同口径一行，异常显示“估值暂不可用”或明确缓存日期。将完整valuation对象放入snapshot_json，保留原有投递键及历史报告内容；旧报告不要求补齐字段。估值不增加周环比分位变化，避免第一版引入额外对齐逻辑。

## 兼容、上线和回滚

迁移仅加表；API仅加字段，前后端可分步部署。Token为空可部署并验证降级。配置Token后用一次人工触发刷新核实数据，再等待原定时周报。任何真实推送验证需使用明确测试渠道，不能为了测试重复发生产周报。

回滚代码可保留新增表；清空Token立即停用后续理杏仁请求，原行情与周报继续工作。不删除历史报告或行情表。

## 未实测项目与实施门槛

- 官方文档：https://www.lixinger.com/api/open-api/html-doc/cn/index/fundamental （2026-11-02核实）。示例指数是000016，不能作为沪深300真实数据。
- 尚无用户Token，账号权限、套餐费用、沪深300目标日实际返回和周五19:00更新及时性仍待真实联调。
- 上述未知不阻碍离线实现，但禁止声明真实接入成功；上线验收必须标明是否完成联调。不得擅自付费开通服务。
- 分位算法使用理杏仁供应商口径，不承诺与自算严格小于比例或其他站点完全一致。
