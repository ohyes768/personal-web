# Journal - jackson.tang (Part 2)

> Continuation from `journal-1.md` (archived at ~2000 lines)
> Started: 2026-10-28

---



## Session 52: 归档地图数据补齐父任务

**Date**: 2026-10-28
**Task**: 归档地图数据补齐父任务
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

归档 10-16-map-data-backfill 父任务（按方案演进）：两个子任务已各自归档，但原跨子验收「线上出现 12 个 osm-building 轮廓」未达成——2026-10-28 核对线上为 160 展示小区、135 osm 轮廓、25 无轮廓且无任何 osm-building；交互式方案已由 10-28 接手实现，剩余线上补齐随其部署窗口处理。

### Main Changes

### Main Changes

- 归档 `10-16-map-data-backfill`（父任务），按方案演进归档。两个子任务 boundary-estimate-script（ef61c7d，cb5d871 重构为脚本与后台共用 boundary_estimate）与 boundary-upload-api（ffdef53，写入锁改用共享 boundary_publish 发布锁）已先各自归档。
- 父任务原跨子验收第 2 条「端到端 → 线上地图出现 12 个 osm-building 轮廓」**未达成**，已在 prd.md 与 task.json notes 中如实记录：2026-10-28 只读核对线上 /api/map/communities 为 160 个展示小区、135 个 osm 轮廓、25 个无轮廓，来源分布无任何 osm-building，即脚本 --apply 从未在生产执行；缺口已从 10-16 摸底的 12 扩到 25（期间新增 local-* 前缀新房/在建小区），原「补齐 12 个」目标本身已过期。
- 交互式生成/预览/确认应用/撤销已由 `10-28-housing-boundary-preview` 接手并实现（cb5d871，SQLite 覆盖层分层：基础层 + 人工确认覆盖层，后台重建不吞人工结果，撤销只删覆盖层），本父任务的脚本 + 上传接口方案在生产补轮廓上已被其取代，剩余线上补齐随 10-28 部署窗口处理。
- 本地 estimate_out 实跑记录：12 个无轮廓小区产出 11 个候选，朗庭(1024) 无建筑可聚类、兴耀鑫都汇(167483594) 仅 1 栋低置信，均未上传。探测线上用的临时 json 已删除，未改任何生产数据。

### Testing

- 本轮未新增代码改动，沿用已归档子任务的验证结果：后端全量 968 passed、前端 130 项/tsc/lint/build 通过。

### Status

[OK] **Completed** — 父任务按方案演进归档；线上补齐未完成的部分移交 10-28。

### Next Steps

- `10-28-housing-boundary-preview` 实现完成（cb5d871），遗留浏览器端手工 QA 与线上部署待授权；部署后可用其交互入口为线上 25 个无轮廓小区逐个生成并确认轮廓。
- `10-12-community-price-transactions` 仍在 planning，未动代码。
- `00-bootstrap-guidelines` 按 notes 保留进行中。


### Git Commits

| Hash | Message |
|------|---------|
| `ef61c7d` | (see git log) |
| `ffdef53` | (see git log) |
| `cb5d871` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

---

## Session 53: 完成已收录小区多选合并

**Date**: 2026-10-28
**Task**: 已收录小区多选合并（10-28-community-merge-ui）
**Package**: apps/housing-map
**Branch**: `master`

### Summary

接手上一会话遗留的合并 UI 实现（代码已写、未提交、未验证），完成文案修正、隔离环境端到端验证、
提交与归档。线上水晶城 3 条重复记录由用户自行在页面合并，未触碰生产数据。

### Main Changes

- **修正合并预览文案（b19051e）**：后端 `_merge` 只补 `address/district/longitude/latitude/coordinate_system`
  这些 payload 字段，**不迁移 `amap_position`**（高德 POI 匹配结果）。原预览写"保留方缺失，将补入被并方定位坐标"
  与实际不符，改为按 `has_coordinates` 表述并加一行"高德 POI 匹配结果不随合并迁移"提示；
  另修 "无法拍记录" 语病为 "暂无拍卖记录"。
- **前端实现**（上一会话产出，本次提交）：`MergeDialog.tsx`（保留方单选 + 预览 + 逐条提交）、
  `DirectoryFlowWorkspace.tsx`（admitted 模式选择列、批量条、翻页/筛选清空选择）、
  `globals.css`（`.catalog-selectable.catalog-admitted` 8 列列宽、窄屏隐藏选择列）。
- **隔离验证环境**（`.tmp-merge-verify/`，验证后已删除）：`HOUSING_DATA_DIR` 指向副本 data 目录的后端 +
  `HOUSING_API_ORIGIN` 指向该后端的前端副本，造 5 条假小区（甲有坐标/new_house、乙无坐标、丙无坐标2来源、
  租甲/租乙各有 fang matched 来源）。
- **spec 新增** `guides/housing-map-merge.md`：合并语义表、admitted 硬门槛与"本地库已收录列表为空"的原因、
  隔离验证环境做法（Next dev 跨域保护、造数唯一约束、进程残留导致目录删不掉）、选择列列宽约定。

### Testing

- `pnpm lint` / `pnpm build` 通过（apps/housing-map）。
- 浏览器端到端（隔离环境，端口 3010/8099）：预选规则（有坐标优先于来源多）、混合市场状态警告与按钮文案、
  逐条失败（"两个小区都有租金来源"原样透出，失败项仍在列表）、成功合并（5→3 条、保留方别名含被并方名称与别名）、
  宽屏列宽 4/24/10/16/12/10/14/10、不收录 Tab 0 checkbox、窄屏 502px 卡片态不塌无横向溢出。
- 开发库与生产库数据未改动（主库 meta 与 admission 行核对一致）。

### Status

[OK] **Completed** — 任务归档至 `.trellis/tasks/archive/2026-10/10-28-community-merge-ui`。

### Next Steps

- 线上水晶城水晶澜轩 / 钱江水晶城 / 钱江水晶澜轩 三条由用户在「已收录」页自行合并（实施者不碰生产数据）。
- `10-12-community-price-transactions` 仍在 planning，未动代码。

### Git Commits

| Hash | Message |
|------|---------|
| `b19051e` | feat(housing-map): 已收录小区多选合并 |
| `5d0878d` | docs: 记录小区合并契约与隔离验证环境做法 |
| `003809e` | chore: 归档已收录小区多选合并任务 |


## Session 53: 补齐楼盘地点与类型全量更新

**Date**: 2026-10-29
**Task**: 补齐楼盘地点与类型全量更新
**Package**: housing-map
**Branch**: `master`

### Summary

新增更新全部/继续匹配/重试失败三个入口；refresh_all重新查询自动结果并保护人工决定，旧all保持补缺兼容。后端1093和前端169测试通过，lint/tsc/build通过，1440/390静态预览无溢出。用户已授权提交并推送，未部署。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

随本次 housing-map 功能提交。

### Testing

- 后端1093与前端169测试通过；lint、类型检查和生产构建通过；1440/390静态预览无溢出。

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 54: 评级任务连续排队与队列实时展示

**Date**: 2026-10-29
**Task**: 评级任务连续排队与队列实时展示
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

废止评级 400 拒绝旧契约，改为运行中受理追加（append_codes 持久化、FIFO 派发、收尾窗口互斥）。前端单一轮询生命周期 + 队列面板（分区展示、每秒计时、逐股禁用）。后端 298、单测 13、e2e 18 全过；审查修复 _run_one 异常兜底防队列挂起（HIGH）。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `ec68ff0` | (see git log) |
| `7e4262b` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 55: 租金两个按钮收进同一区块并收尾任务

**Date**: 2026-10-29
**Task**: 租金两个按钮收进同一区块并收尾任务
**Package**: backend/housing-map
**Branch**: `master`

### Summary

housing-map：采集任务弹窗里「匹配租金来源」与「更新租金数据」收进同一「租金流程」区块（.directory-task-group），桌面与 390px 实测无溢出；前端 171 项测试、tsc、lint 通过。10-29-housing-rental-source-unification 归档，未完成项（R1 剩余验收、R2 通道级断点、R3 独立迁移工具、R4 全量上线）转入新任务 10-29-housing-rental-source-followup。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `2f18938` | (see git log) |
| `98e3ddc` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 56: 股息率五维评分与 skill 版本追踪

**Date**: 2026-10-29
**Task**: 股息率五维评分与 skill 版本追踪
**Package**: backend/dividend-select
**Branch**: `master`

### Summary

五维分数与版本合并为单列 4/4/3/2/1（v1.1.1），点击打开报告；skill 4.3.0 确定性输出版本，保存版本并标识需重评，隔离旧缓存。后端64/skill199/浏览器18项通过，TypeScript通过。部署需配置实际 skill 版本来源。

### Main Changes

- 紧凑五维结果、未知维度占位及实际 skill 版本展示。
- skill 输出版本落盘、部署版本对比与 Hermes 缓存隔离。

### Git Commits

见本次功能提交及独立 skills 仓库的 4.3.0 版本合同提交。

### Testing

- 后端 64 项、skill 199 项、浏览器 18 项及 TypeScript 检查通过。

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 57: 关闭幸福里来源旧收尾任务

**Date**: 2026-11-03
**Task**: 关闭幸福里来源旧收尾任务
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

按用户要求关闭并归档 10-29-housing-rental-source-followup：独立迁移工具取消，已完成断点复用及构建记录保留，其余未验收事项关闭且不宣称通过。仅整理任务文档，未改产品代码或生产数据。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

(No commits - planning session)

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete

## Session 58: 股息率页面加载提速实施

**Date**: 2026-11-04
**Task**: 11-02-dividend-page-load-speed
**Package**: backend/dividend-select + apps/dividend
**Branch**: `master`

### Summary

实施页面加载提速：后端以源文件签名 (path, mtime_ns, size) 缓存股东/财务/申万/M120
派生快照（失败不发布、并发构建去重），读取类路由同步 Pandas 组装移入 asyncio.to_thread，
/stocks 新增 codes 精确过滤；前端主列表/全量 M120/stats 仅"全部"Tab 加载，挡位监控
深链接只发收藏 codes 资料与精确现价请求，去重初始化时的重复 financial/status。

### Main Changes

- 新增 versioned_snapshot.py 与 ShareholderReader/FinancialReader/StockInfoService/
  M120Service 的签名缓存；修复申万映射加载一次永不更新的既有缺陷
- routes.py：health/stocks/m120/prices/m120-status/financial-status 提取同步构建函数进线程池
- page.tsx/hooks.ts：enabled 按 Tab 请求、响应序号防竞态、alertStocks 占位兜底（现价
  链只依赖挡位代码）、挡位弹框无 M120 时用 /prices 降级
- 新增 tests/test_snapshot_cache.py 24 用例；spec 新增 snapshot-cache-contract.md

### Testing

- 后端全量 355 passed / 3 skipped；唯一失败 test_quality_service 队列排序为改动前
  即存在的 flaky（stash 对照 3/3 复现）
- 前端 tsc --noEmit 零错误；next build --no-lint 编译与静态生成通过（lint 阶段由
  并行任务 11-04-eslint 的 api-client.ts 存量 error 阻塞，非本任务范围）
- 浏览器验证：/tab=alerts 深链接不再请求全量 stocks/M120/stats，挡位 bar 完整渲染；
  本地并发压测 health p95 374→226ms。详见任务 research/measurement-local.md

### Status

[OK] **Completed**（NAS p95 复测与部署按 PRD 另行授权后执行）

### Next Steps

- 部署授权后在 NAS 按 baseline.md 方法复测 30 次冷/热 p95


## Session 58: index-trends 移除推送职责并保留 Web 每日刷新

**Date**: 2026-11-05
**Task**: index-trends 移除推送职责并保留 Web 每日刷新
**Package**: backend/index-trends
**Branch**: `master`

### Summary

移除周报生成、钉钉发送、每周调度、启动补发与控制接口，保留 Web 工作日16:30行情和估值刷新、手动刷新、只读状态API及历史周报。后端200项、前端9项测试通过，类型检查和构建通过；未部署。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `2a683b53` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 59: 抖音文字稿定时任务页面化：内建调度管理 + 执行历史

**Date**: 2026-11-06
**Task**: 抖音文字稿定时任务页面化：内建调度管理 + 执行历史
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

douyin-processor 参照 dividend/macro 内建调度模式新增 src/scheduler 包（4 个管理 API、enabled.json overlay 持久化、JSONL 执行历史、多 cron 拆子 job）；前端加齿轮入口与 SchedulerModal 弹框（启停/立即执行/历史）；旧 /api/process/pending 委托 manager 且落 manual 历史。pytest 19/19、build 通过、本地前后端联调截图验证。踩坑已沉淀 spec：start 期 pause 需显式传 scheduler 实例、AsyncIOScheduler 测试须在事件循环内启动。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a28e261b` | (see git log) |
| `ec2e6e52` | (see git log) |
| `c2ba5cfa` | (see git log) |
| `1f1274ee` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 60: kids 设备歌单浏览器播放：补齐 PRD 缺口并上线

**Date**: 2026-11-11
**Task**: kids 设备歌单浏览器播放：补齐 PRD 缺口并上线
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

盘点发现任务主体（后端 tracks 接口/nginx 静态路由/候选行播放器）已落地并上线，本轮补齐 PRD 缺口：播放器加上一首/下一首、移动端 playsInline、「当前设备歌单」表新增操作列可按编号播放、后端 /api/collections 增加 published 字段（上月发布的合集也能播）、生成中禁用播放。修掉两个自引入问题：同集合在候选区与设备歌单表重复渲染两个播放器导致重复出声；390px 下合集名称被挤成一字一行。NAS 实测：/kids-audio Range 206、tracks 接口 200/404、线上播放与下一首切歌正常、390px 无横向滚动。后端 pytest 245 passed/1 skipped，2 条失败在干净树上同样复现（Windows 磁盘慢 + 顺序偶发）。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `3573ac9f` | (see git log) |
| `bff06dae` | (see git log) |
| `ec3b704e` | (see git log) |
| `17633de6` | (see git log) |
| `ffcb168a` | (see git log) |
| `4eda04ff` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 61: Dividend 全部页股票搜索上线——完整收集池匹配与星标复用

**Date**: 2026-11-11
**Task**: Dividend 全部页股票搜索上线——完整收集池匹配与星标复用
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

后端 /stocks?search= 在完整收集池按名称/代码包含匹配（zfill6 保留前导零、忽略股息率阈值、codes 取交集、相关度排序、纯读不采集）；前端「全部」页搜索条（300ms 防抖+序号防旧覆盖），显示分支=搜索>只看收藏>阈值列表，结果复用星标收藏；无匹配明确空状态；useTechnicalData 改全量 M120 Map 派生避免搜索重拉。验证：后端 380 passed（新增 21 例）、前端 tsc/lint 0 error、45 单测、4 e2e、真实 uvicorn 联调确认阈值绕过与 codes 交集。沉淀 .trellis/spec/backend/dividend-select/backend/stock-search-contract.md。已知既有失败（stash 对照证明与本次无关）：test_quality_service flaky、quality-reader 布局 e2e、Windows standalone symlink 构建限制。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `88f5bc1c` | (see git log) |
| `73a546da` | (see git log) |
| `298bb542` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 62: kids 浏览器播放改为底部悬浮播放条

**Date**: 2026-11-11
**Task**: kids 浏览器播放改为底部悬浮播放条
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

把设备歌单页的行内播放器改成固定在视口底部的悬浮播放条：播放条为页面级单例（候选区与设备歌单表共用状态），原生 audio controls 保留暂停/拖动/音量，上一首/下一首与曲目抽屉（向上展开、当前曲高亮）齐备，占位留白避免遮挡内容并适配 iPhone 安全区。顺带清掉行内播放器的死 CSS，修掉 390px 下抽屉越界与候选行标题一字一行。NAS 实测桌面与 390px 均只有 1 个 audio 实例、播放条贴底、无横向滚动。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `cf441fd0` | (see git log) |
| `a00c4ab8` | (see git log) |
| `b3054d8a` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 63: NAS 服务管理台 V1（台账 + 只读 Docker 发现 + URL/TLS/Release 检查）

**Date**: 2026-11-11
**Task**: NAS 服务管理台 V1（台账 + 只读 Docker 发现 + URL/TLS/Release 检查）
**Package**: backend/service-manager
**Branch**: `master`

### Summary

按 Trellis 任务 11-11-nas-service-manager 完成 V1：后端台账/发现/投影/检查/备份/认证（171 tests），前端五页 + 16 e2e，compose/nginx/deploy/首页/文档/spec 全部接线；NAS 实机部署待授权。

### Main Changes

### Summary

按 `.trellis/tasks/11-11-nas-service-manager` 的 PRD/design/implement 完成 NAS 服务管理台 V1（M1–M6）。
后端 `backend/service-manager`：SQLite 人工台账（服务/组件绑定/入口/手工端口/仓库关联/忽略决定）+ 只读
Docker 发现（socket-proxy，inspect 白名单投影，稳定 source_key）+ 端口/域名/证书投影 + URL/TLS/GitHub
Release 检查与单 worker 调度 + 备份导出恢复 + 单管理员认证。前端 `apps/service-manager`（basePath
`/services`，端口 3012）五个页面：服务列表、详情、资源总览三标签、发现导入、设置。
接线 `docker-compose.nas.yml`（frontend/backend/socket-proxy 三容器 + `sm-docker-net` internal 网络 +
`service-manager-data` 卷）、`nginx/web.conf` 三件套、首页卡片、`deploy-nas.sh` 四处、dev 脚本、文档与 spec。

### Main Changes

- 状态维度严格分开：runtime/health/url/tls/release 各自枚举；聚合 health 里 `not_configured` 优先级高于
  `healthy`——只要有一个 required 组件没配健康检查，服务级不许显示「健康」。实测 NAS 上 dividend-frontend
  未配 health，详情页因此显示「未配置健康检查」而非绿灯。
- 端口重叠只按「同主机+同协议+同地址族+IP 绑定重叠+同宿主端口」判定；容器内部 expose 与 stopped 容器的
  historical 映射都不算占用；host 网络明确标「未自动采集」；页面永久带「不能据此证明端口空闲」提示。
- Docker 只读两层保险：代码层只调 version/ping/list/inspect 并立即投影白名单字段（Env/Cmd/Hostname 永不落库），
  部署层 socket-proxy `POST=0` + 类别关闭；采集失败不发布半份快照，`missing` 只由成功全量扫描产生。
- 证书 `invalid` 带原因（self_signed / hostname_mismatch / expired_chain / untrusted_ca）。实测 NAS 全线自签
  泛域名证书 → 显示「无效 · 自签证书 · 2036-06-22 到期」，而不是笼统的红灯。
- 备份恢复三步不可省：preview 拿 digest+revision → 用同一份字节 restore → 校验后先 SQLite backup 再单事务
  替换；恢复清空 check_results/release_reads 并把 release 基线归零。
- 开发期 Origin 校验补第三条通路：Origin 与 `X-Forwarded-Host` 同源且直连方是回环地址（Next dev rewrite 会
  改写 Host）；生产 nginx 保留 Host 走第一条，不依赖可伪造的头。

### Testing

- 后端：`uv run python -m pytest tests/ -q` → **171 passed**（11 个文件，覆盖 A1–A13 契约面）
- 前端：`pnpm exec eslint .` 0 problems；`pnpm exec tsc --noEmit` 0 error；`pnpm build` 成功
- e2e：`pnpm exec playwright test` → **16 passed**（8 用例 × desktop/375px）
- 静态：`nginx -t`（挂真实 ssl）successful；`docker compose config --quiet` 通过；`bash -n deploy-nas.sh` 通过
- 真实环境：本机即 NAS 宿主，后端实测扫到 51 个组件 / 45 个候选 / 13 个 compose 项目；浏览器走通
  登录 → 导入 dividend 前后端 → 详情 → 资源总览 → 真实 URL/TLS 检查。

### 踩坑与修正

- Next dev rewrite 会把 Host 改写成后端地址 → Origin 校验把正常写操作 401。补 loopback + X-Forwarded-Host 通路。
- cookie Path 写 `/api/services` 会让后端直连/开发 rewrite 全部 401；改成 `/api`（仍只发给 API）。
- `pnpm build` 会清 `.next`，正在跑的 dev server 随即 404/500；验证顺序必须是 build 之后重启 dev 再跑 e2e。
- Playwright 自带 Chromium 装不下来（缓存目录只读 + CDN 不通）→ `channel: "chrome"` 复用宿主机 Chrome。
- 发现页表格被长容器名撑到必须横向滚动 → 加 `table.cols-fit` + `col-*` 宽度类 + truncate。

### 未执行（需授权）

- NAS 实机构建部署（`deploy-nas.sh service-manager both` + `nginx`）与 socket-proxy ACL 六条探针冒烟
- proxy 镜像 digest 锁定（当前 `tecnativa/docker-socket-proxy:0.2.0` tag）
- 专用验收实例的数据恢复/回滚演练


### Git Commits

(No commits - planning session)

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 64: 服务管理台验收复核：补 cookie 属性测试与 nginx 裸路径兜底

**Date**: 2026-11-11
**Task**: 服务管理台验收复核：补 cookie 属性测试与 nginx 裸路径兜底
**Package**: backend/service-manager
**Branch**: `master`

### Summary

第二轮复核 A1–A14 证据：核对全部引用测试名、补 4 条 cookie 属性断言（171→175）、补 /api/services 无尾斜杠 location 兜底并用隔离 nginx 实测转发路径；全量测试/构建/e2e 16 用例全绿。

### Main Changes

### Summary

第二轮：对 V1 交付做证据复核，而不是重复劳动。逐条核对 implement.md 里 A1–A14 引用的测试名是否真实存在
（全部命中），并针对两处「标了 ✅ 但证据不足」的点补实证。

### Main Changes

- **补 cookie 属性测试（A13 的真实缺口）**：此前 A13 标 ✅ 但没有任何用例断言 `HttpOnly` /
  `SameSite=Strict` / `Path` / `Secure`。新增 4 条单测，锁定 starlette 实际输出形态
  （`HttpOnly; Max-Age=43200; Path=/api; SameSite=strict; Secure`），并显式断言
  `Path` 不能写成 `/api/services`（写错会让后端直连与开发 rewrite 全部 401）。后端 171 → 175。
- **补 nginx 裸路径兜底（A14 的真实缺陷）**：`location /api/services/` 带尾斜杠，`GET /api/services`
  不匹配任何 location → 生产 404；而开发期 Next rewrite 的 `:path*` 能匹配，属于「本地正常、生产炸」。
  按 spec §4 ③' 补 `location = /api/services` 精确转发，并用一次性 nginx 容器实测。
- **A14 路由实测（不再只是 nginx -t）**：起隔离 nginx（独立网络 + 19443 避开生产 80/9443）+ 两个桩上游，
  逐条确认转发路径：`/api/services/health`→`/api/health`、`/api/services/services`→`/api/services`、
  `/api/services`→`/api/services`、`/api/services/summary`→`/api/summary`、页面与 `_next/static`
  带 `/services` 前缀转前端。全部符合契约。
- 修正 implement.md 里 test_tls_probe 的用例数（写 17，实际 16）；用例数统一 171 → 175。

### Testing

- 后端 `pytest tests/ -q` → **175 passed**
- 前端 `eslint .` 0 problems；`tsc --noEmit` 0 error；`pnpm build` 成功
- e2e `playwright test` → **16 passed**（desktop + 375px）
- `nginx -t`（挂真实 ssl）successful；`compose config --quiet` 通过；`bash -n deploy-nas.sh` 通过

### 踩坑与修正

- e2e 发现页断言写太窄：后端未配 `DOCKER_HOST` 时页面走「Docker 不可用」分支，而断言只认「没有匹配的候选容器」。
  已覆盖三种正常终态（候选表格 / 无匹配候选 / Docker 不可用）。
- 反复试隔离 nginx 时踩到：host 网络会和生产 nginx 抢 80/9443 端口，导致 bind 失败并误读成「配置 404」；
  最终用独立网络 + 发布 19443 才干净复现。
- `~/nginx/web.conf` 是仓库文件的符号链接，内容一致；生产 nginx 已加载 service_manager 段（7 处），
  只是后端容器还没起，所以线上如实返回 502/解析失败。

### Status

代码与接线完成，可执行验证全绿。仍待用户授权：实机构建部署、socket-proxy ACL 冒烟、proxy digest 锁定。


### Git Commits

(No commits - planning session)

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 65: 经理 tab 样式统一与刷新入口

**Date**: 2026-11-11
**Task**: 经理 tab 样式统一与刷新入口
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

经理 tab 改为复用 FundsHeader/FilterPanelShell/SortableHeader 与其余 5 tab 统一；新增 GET /managers/refresh 刷新入口（force 全量重采、单飞 409、按人进度、errors JSON 契约）；顺带修复最长任期列错绑 managed_fund_count 且不在排序白名单。581 后端测试通过。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a023440` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 66: 经理筛选三项派生指标：胜率/独管/代表作背离

**Date**: 2026-11-12
**Task**: 经理筛选三项派生指标：胜率/独管/代表作背离
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

落地经理筛选调研结论：任期胜率（中位数55%，识别稳定盈利）、独管比例（识别共管稀释/挂名）、代表作背离（>15pp 标记幸存者偏差，仅展示）。全部由 manager_tenures 聚合不新增采集；API 加 min_win_rate/min_solo_ratio 筛选与排序；前端加列与维度。修复 func.sum(布尔) 返回 Boolean 的类型陷阱（case 显式转整数）。590 测试通过，线上验证胜率≥80且独管≥80 命中 144 人。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `2415110` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 67: 经理筛选分层默认值 + 在管只数筛选

**Date**: 2026-11-12
**Task**: 经理筛选分层默认值 + 在管只数筛选
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

MANAGER_DEFAULT_FILTERS 落地调研分层口径：硬门槛(从业5/规模5亿/只数8)+质量门槛(胜率60/独管50)，收益回撤不默认卡。新增 max_fund_count 参数与面板维度。默认组合命中 200 人。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `a410b5f` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 68: 经理年化双口径拆分：含离任 + 在管

**Date**: 2026-11-12
**Task**: 经理年化双口径拆分：含离任 + 在管
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

weighted_annual 原含离任段（职业生涯口径）；新增 current_weighted_annual 仅在管段（当下状态），派生指标模式不新增采集。前端双列并排+悬停口径说明，两口径背离即状态信号（江峰 21.8%→-19.7%）。594 测试通过。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `162e9a1` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 69: 服务管理台实机上线：部署前置检查 + 修生产写操作 401

**Date**: 2026-11-12
**Task**: 服务管理台实机上线：部署前置检查 + 修生产写操作 401
**Package**: backend/service-manager
**Branch**: `master`

### Summary

修 deploy-nas.sh 缺前置检查（自动生成 .env 两项并打印口令）；修 nginx $host 不含端口导致所有写操作 401（nginx 改 $http_host + 后端同源判断放宽，175→178）；实机三容器上线，冒烟与 socket-proxy ACL 12 条探针全过。

### Main Changes

### Summary

实机部署并验收 NAS 服务管理台。用户在 NAS 上执行 deploy-nas.sh 时撞到
「required variable SERVICE_MANAGER_ADMIN_PASSWORD is missing」，本轮定位并修掉它，
继续把部署跑完，最后发现并修掉一个更隐蔽的生产缺陷（写操作全 401）。

### Main Changes

- **部署脚本前置检查**：service-manager 与 all 目标在构建前检查根 .env 的管理口令与签名密钥，
  缺失时自动生成随机值写入（.env 权限收 600）、空值就地替换不追加重复键，并把登录口令打印在终端。
  用户不再需要先读文档再手工填 .env。
- **nginx `$host` 不含端口 → 写操作全 401**：nginx 文档里 `$host` 是去端口的 host 名，
  浏览器 Origin 带端口（https://host:9443），字面比较必然不等 → Origin 校验失败；
  登录路由本就没挂 Origin 校验，所以「登录能过、其它写操作 401」这个症状极具迷惑性。
  两处同改：nginx 改 `$http_host`；后端同源判断放宽到 hostname+scheme 相同（跨站仍拒绝）。
  后端用例 175 → 178。
- 契约与文档：后端 spec 与 new-service-onboarding 增补「Host 头必须带端口」条目；
  setup 文档补免填 .env 说明与实机上线记录。

### Testing

- 后端 `pytest tests/ -q` → **178 passed**；eslint 0 problems；tsc 0 error
- `nginx -t` / `compose config --quiet` / `bash -n` 全通过
- 实机：三容器上线（backend healthy）+ nginx reload
- 冒烟：页面 200 / 静态资源 200 / health 200 / 未登录 401 / 裸路径 401（兜底生效）/
  登录 cookie（HttpOnly + Path=/api + Secure）/ 写操作 201
- socket-proxy ACL 12 条探针：仅 containers/json、version、_ping 为 200，其余 9 类全 403
- 容器隔离：proxy PortBindings={} 且只在 internal 网络；后端 Binds 只有数据卷，无 docker.sock
- 真实导入 dividend 前后端 → runtime=running、health=not_configured（未配 healthcheck
  故不显示「健康」）、URL=unreachable + 自签原因、TLS=invalid + self_signed + 3510 天到期

### 踩坑与修正

- buildx 报 `open ~/.docker/buildx/activity/.tmp-xxx: permission denied` 不是真权限问题，
  是会话沙箱限制（工作区外路径）；改用提权执行部署命令解决。
- 反复用 host 网络起隔离 nginx 会和生产 nginx 抢 80/9443 端口，报错「Address in use」
  被误读成配置 404；最终改用独立网络 + 发布 19443 才干净复现。
- 排查 401 时先怀疑了 CSRF 逻辑本身，实际是 Host 头语义差异——先打印反代实际传的
  Host 再看后端判定，能省很多弯路。

### Status

已上线并推送（dfc7bc3）。仍未做：破坏性恢复/回滚演练（需独立数据卷）、proxy 镜像 digest 锁定。


### Git Commits

(No commits - planning session)

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 70: 经理详情拆在任/已离任双 tab

**Date**: 2026-11-12
**Task**: 经理详情拆在任/已离任双 tab
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

展开详情的历任基金由单表混排改为 pill 双 tab（在任默认/已离任），说明文案随 tab 切换口径，空分组空态文案。线上双向切换验证通过。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `8a11b2a` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete


## Session 71: 经理↔基金双向关联：徽章跳转+在榜汇总+反向链接

**Date**: 2026-11-12
**Task**: 经理↔基金双向关联：徽章跳转+在榜汇总+反向链接
**Package**: backend/douyin-processor
**Branch**: `master`

### Summary

三层闭环上线：1) 经理详情任期基金代码变可点徽章（归属tab+在榜N周），点击跳对应tab自动开抽屉；2) 经理列表行挂『在榜N』汇总；3) 基金抽屉经理名可点回经理页。URL 协议：tab ?code= / 经理 ?keyword= / 榜单 ?focus=。踩坑：basePath 下 Link href 不能带 /funds 前缀；抽屉 stub 模式依赖数组须用 effective?.code；discovery 无自有详情端点。597 测试通过，线上双向跳转验证通过。

### Main Changes

- Detailed change bullets were not supplied; see the summary above.

### Git Commits

| Hash | Message |
|------|---------|
| `8bf41c2` | (see git log) |

### Testing

- Validation was not recorded for this session.

### Status

[OK] **Completed**

### Next Steps

- None - task complete
