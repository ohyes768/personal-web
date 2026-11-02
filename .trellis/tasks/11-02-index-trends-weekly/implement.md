# 周线调整实施计划

状态：第 1–5 节已在代码和自动化测试中落地。第 6 节（规范文档、数据库副本演练、部署、真实投递）未做。

## 1. 数据边界与纯计算（AC1—AC4）

- [x] 阅读prd.md、design.md、research/current-state.md以及implement.jsonl中规范；确认当前工作区和目标路径，不碰其他住房任务改动。
- [x] 在backend/index-trends/tests/test_weeks.py、test_weekly_validate.py先写失败用例：跨年周、周五15:04/15:05、节假日短周、整周休市、缺失应有周、日历越界、2月29日10年窗口边界。
- [x] 在src/core/weeks.py定义周主键、自然周坐标、日历区间和固定窗口归属；在src/data/trading_calendar.py封装XSHG会话表并注入测试日历；在src/data/validate.py增加周序列校验。新增依赖与uv.lock必须只在实施阶段变更。
- [x] 给src/core/regression.py增加显式x坐标的周线计算入口及新算法版本；旧入口、旧月线基准保持可验证。新增test_weekly_regression.py使用可手算的非等距样本验证OLS、前移一周deviation、全周休市时间间隔及非法宽度。
- [x] 实施时抓取并保存脱敏只读周Kfixture与日历来源/覆盖日期，独立生成数值基准；测试不联网。检查1600条请求确实覆盖首发周，数据日期和日历不匹配必须记录并解决，不能跳过验证。
- [x] 扩展provider.py周周期适配并测试部分周、重复周、OHLC与非有限值；所有新测试先确认因缺功能失败，再实现并复跑。

## 2. 存储与原子模型（AC3、AC4、AC7）

- [x] 在tests/test_weekly_store.py构造有旧月线模型、旧sent/no_channel周报和自定义配置的SQLite库，先测试重复迁移不丢数据、不重复投递。
- [x] 修改src/services/store.py加入独立周线表、schema_migrations、snapshot_id、report_attempts与snapshot_json；保留原月线表，不把months列改装为周数。
- [x] 修改src/core/models.py声明周线kind、带时间坐标的训练哈希和周模型记录；在trend_service.py分离取数校验、纯计算和事务发布。
- [x] 测试同周更新价格模型不变、新完整周产生新版本、旧模型不可覆盖、事务中途失败不发布部分数据。旧成功快照仍可读取且失败状态可见。
- [x] 测试10个日历年选样、固定10年/3年窗口、观察区扰动不改训练结果、成立以来与全历史共用版本。

## 3. API与周报（AC2、AC5—AC7）

- [x] 扩展tests/test_api.py，明确周字段、合法kind、旧kind别名、旧月线ID拒绝说明、空库和数据异常状态。GET不能发消息。
- [x] 修改src/api/routes.py与trend_service.py，按design.md合同返回周K、周轨道、样本数和snapshot_id，不保留装载周值的月命名字段。
- [x] 在tests/test_weekly_report.py先覆盖未完成周手动触发、正常周、短周、整周休市、缺失日线、缺模型、无渠道、发送失败重试、重启、同周sent去重。
- [x] 修改report_service.py：先校验再锁定快照，生成周涨跌与可复算的位置变化拆分；首次周线报告和异常旧报告不可直接比较。旧no_channel报告被替换前保留审计原文。
- [x] 验证页面临时选模型不写周报配置；保留Asia/Shanghai、fri/mon-fri、单实例互斥与有界关闭合同。

## 4. 页面（AC5）

- [x] 修改apps/index-trends/lib/types.ts和api.ts，对齐所有周响应；更新app/page.tsx的默认kind、旧URL映射与数据新鲜度文案。
- [x] 修改components/CurrentTab.tsx、HistoryTab.tsx、TrendChart.tsx，使用周日期/实际收盘日/样本周数，保留原双Tab布局和主题，不做额外重设计。
- [x] 在lib/candleData.test.ts保留OHLC解析回归，并为休市时间槽、未来周'-'和跨年周增加覆盖；图表辅助逻辑需要时提取到lib，避免为了测量镜像整套实现。
- [x] 当前摘要和图形使用同一版本，出现snapshot_id不一致必须重取；切换中不展示旧模型摘要。dataZoom不得触发拟合API。

## 5. 验证命令与证据（AC8）

2026-11-02 实施记录见本节末尾。浏览器与只读真实行情联调本轮没有做。

| 工作目录 | 命令/操作 | 预期 |
|---|---|---|
| backend/index-trends | uv run python -m pytest tests/ -v | 原月线兼容和新周线测试全部通过，沿用项目盘.pytest-tmp |
| apps/index-trends | node --experimental-strip-types --test lib/candleData.test.ts | OHLC、空周占位和图表解析通过；若本机Node不支持则使用已安装可用的TS测试入口，不盲目重装依赖 |
| apps/index-trends | pnpm exec tsc --noEmit | 无类型错误 |
| apps/index-trends | pnpm build | 生产构建成功；pnpm包装器异常时使用本地node_modules的TypeScript/Next CLI并记录实际命令 |
| 浏览器 | 375px/1440px，双Tab、4个固定窗口+全历史、两模型、刷新/返回、tooltip、缩放与控制台 | 日期、图形和摘要一致，无横向溢出或ECharts错误 |
| 后端隔离数据目录 | 只读真实行情联调，不配置notifier，不手动投递 | 返回最新完整周、真实收盘日期及双模型数值；进行中周排除，日历覆盖符合要求 |

该包没有lint脚本，不写“lint通过”。`pnpm build` 日志里的 “Linting and checking validity of types” 是 Next 构建步骤，不是独立的 lint 脚本。

### 2026-11-02 验证记录

工作目录 `backend/index-trends`，pytest 使用 `pyproject.toml` 的 `--basetemp=.pytest-tmp`。

| 命令 | 结果 |
|---|---|
| `uv run python -m pytest tests/ -q --tb=line` | 148 passed，1 warning（Starlette/httpx TestClient 弃用提示），45.85s。这是修正“只查到今天会把周一误判成整周结束”之后的全量结果 |
| `node --experimental-strip-types --test lib/candleData.test.ts`（在 `apps/index-trends`） | 8 passed，0 failed。Node 提示 package.json 未标 `"type": "module"`，测试仍通过 |
| `pnpm exec tsc --noEmit`（在 `apps/index-trends`） | 退出码 0，无输出 |
| `pnpm build`（在 `apps/index-trends`） | 成功。Next.js 15.5.28，静态页 `/` 构建完成 |

脱网周报样例（fixture，不是 11 月 2 日的实时行情）：近 10 年模型 `fit_start=2016-10-31`，`fit_end=2026-10-26`，样本 512 个交易周，算法 `lrc-ltb-week-v1`。2026-10-30 收盘 3985.50，投影周 `2026-10-26`，通道位置 33.2%。一次运行的快照 ID 为 `287f4b275e6e98d3`（由截止周、周线哈希和模型 ID 派生，重复刷新应稳定）。

当时没有做 375px/1440px 浏览器点击，也没有做只读真实行情联调。

### 2026-11-02 16:54 浏览器与只读行情

重启了未带 `--reload` 的 8100，并用空的 `INDEX_TRENDS_DINGTALK_WEBHOOK_URL` 启动。周一未到本周五 19:00，启动补发未跑；`/api/reports` 为空。调度下次周报为 2026-11-06 19:00。页面点「获取最新」后：

- 完整周截止 `2026-10-26`，应完成收盘 `2026-10-30`，日线最新 `2026-11-02`。进行中的 11-02 当周未进入拟合。快照 `0238f17183c5a298`，来源 Tencent Finance，共 1100 个完整周。
- 历史回溯：窗口 1 为 2005-04-04–2015-03-23、507 周；全历史为 2005-04-04–2026-10-26、1100 周。
- 当前通道：近 10 年 512 周、位置 34.6%；成立以来 1100 周、位置 33.1%。11-02 收盘 4016.92 只做投影。页面切换模型后，周报配置仍是 `trailing_10y_weekly`。
- 1440 与 375 均无横向溢出，当前通道有 K 线画布。摘要原先把 11-02 写成「已完成交易周」，已改为「最近收盘」，并标明该周进行中、不参与拟合。
- 没有逐个点窗口 2–4，没有做 tooltip 悬停和 dataZoom 拖拽，没有点浏览器返回。没有部署，没有发钉钉。

调度器源文件未改：`ReportScheduler` 仍使用 Asia/Shanghai、`0 19 * * fri` 与 `30 16 * * mon-fri`，关闭路径仍是有界等待后 `shutdown(wait=False)`。本轮没有单独再跑调度器关闭测试。

`expected_last_complete_week` 改为查到本周日，避免周一收盘后把进行中周当成已完成周。2026-11-02 18:00 的期望截止周因此仍是 `2026-10-26`。

## 6. 上线与回滚准备

- [ ] 更新.trellis/spec/frontend/index-trends-echarts.md周口径及新增周线数据/迁移合同，保留旧记录来源；按质量检查结果完善文档。
- [ ] 用数据库副本完成迁移、重复启动、旧报告审计和新周快照回归，形成备份及恢复步骤。
- [ ] 后续有明确部署授权时再构建、成套替换前后端，检查API/图形/调度及旧数据；真实钉钉投递需单独配置并验收，未配置则报告no_channel。
- [ ] 回滚时先停新服务，恢复旧镜像和迁移前数据库，再启动；保留新数据副本和发送审计，不删除卷，不自动重发历史报告。
