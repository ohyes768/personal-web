# 验证记录：幸福里租金来源自动匹配与按需探查

日期：2026-10-29。本机验证，未写生产关联、未触发生产采集、未部署。

## 1. 实施前技术门

见 `research/probe-feasibility.md`。结论：平台内存在完整可执行发现链，只依赖 `m.xflapp.com`；
原设计里“需要外部搜索引擎”和“可能需要 99hdf 域名”两条前提均不成立，已回写 `design.md`。

真实只读烟测（本机、请求间隔 ≥6 秒、请求计数 3）：

| 步骤 | 结果 |
|---|---|
| 二手房搜索 `full_text=白金海岸花园`（**内部全名**） | 命中总小区 `6581009489657331972`，平台名“白金海岸” |
| 二手房搜索 `full_text=白金海岸` | 同一 ID |
| 租房搜索 `full_text=白金海岸` | `items=[]`（与研究一致，租房通道漏查该小区） |
| 读主页 `/xiaoqu/hz-6581009489657331972.html` | 名称“白金海岸”、地址“香溢路88号”、GCJ02 (120.188369, 30.203001)、`rentInNeighbor.total=31`、种子 3 个 |
| 种子 `7406856173871235098` 详情页归属 | `neighborhood_id=6581009489657331972` ✓ |
| 同小区列表归属 | 全部 `neighborhood_id=6581009489657331972` ✓ |

与本地目录真实记录（`10000281 白金海岸花园`，别名“香溢海岸花园”，坐标 120.18828/30.202926）比对：

- 证据：`名称高度相似` + `位置接近（100米内）`（实测约 12 米）；
- 缺口：`平台名称与目录名称不完全一致`；
- 冲突：无 → **可人工选择**，但**不自动绑定**（名称非精确一致）。

即 A5 的“名称→候选主页→页内房源→正确列表ID”链条在真实数据上成立，且实现没有硬编码本次的 URL/ID：
种子来自主页的 `rentInNeighbor`，ID 来自搜索响应。

## 2. 自动化验证

后端（`backend/housing-map`，Windows `.venv/Scripts/python.exe`）：

```
.venv/Scripts/python.exe -m pytest tests/ -q --basetemp=<独立目录>
→ 1075 passed, 1 skipped
```

新增/改动相关套件单独结果：

| 套件 | 结果 |
|---|---|
| `tests/test_xingfuli_discovery.py`（新增） | 14 passed |
| `tests/test_rental_probe.py`（新增） | 12 passed, 1 skipped |
| `tests/test_rental_xingfuli_sources.py`（新增） | 9 passed |
| `tests/test_xingfuli_rentals.py` `test_xingfuli_pilots.py` `test_rental_providers.py` | 26 passed（传输层抽取后无回归） |
| `tests/test_rental_association_flow.py` `test_rental_refresh.py` | 44 passed |

前端（`apps/housing-map`）：

```
node --test tests/*.test.cjs        → 167 passed
npx tsc --noEmit                    → 无错误
npm run lint                        → 无告警无错误
npx next build --webpack（隔离目录）→ 构建成功，/ 与 /_not-found 静态预渲染
```

隔离构建说明：3007 端口有别的会话在跑 dev server，`next build` 与 `next dev` 共享 `.next` 会互相清缓存，
因此把源码复制到 `F:\tmp-housing-build`、`node_modules` 用目录联接后在该目录构建。Turbopack 拒绝指向项目根之外的
联接（`Symlink [project]/node_modules is invalid`），故改用 `--webpack` 构建器；构建结束后已删除临时目录。

## 3. 验收项逐条核对

| 验收 | 结论 | 依据 |
|---|---|---|
| A1/R1 | 通过 | 目标集合用 `eligible_communities`（目录 admitted + 滨江）；已有来源的小区在 `ProbeService._community` 直接拒绝探查；写入前 `_bind` 重查 `protected()`/`active_source()`，`_human_veto` 重查人工拒绝、准入锁与审核锁 |
| A2/R2 | 通过 | `evaluate` 要求精确名称 + （地址一致或 GCJ02 ≤100 米）+ 无分期/区域冲突；分区变体、异名、异地、缺证据均有负例测试 |
| A3/R3–R4 | 通过（自动化覆盖 API 与状态；浏览器交互未做） | `POST/GET /rental-source/probe`、`/probe/select`；同小区重复 `start` 返回同一活动任务；候选展示名称、地址、坐标、证据与缺口 |
| A4/R4–R5 | 通过 | `selected_page` 与租金来源分离；只有入口核验通过才 `bind_source`；`entry_not_found` 与 `listing_owner` 不匹配都不建绑定；重试不需要链接 |
| A5/R3–R5 | 通过（真实只读链路见第 1 节） | 真实请求复现“名称→候选主页→页内房源→正确列表ID”；实现不硬编码 URL/ID |
| A6/R6–R7 | 部分通过 | 前端已无 URL 输入、粘贴表单与“去外部找链接”提示（`tests/rental-probe.test.cjs` 断言）；各失败原因有独立文案与重试。**桌面/390px 浏览器实测未做** |
| A7/R5–R6 | 通过 | 新关联只写 `sources`（provider+真实 ID，seed 独立字段），采集沿用 `XingfuliClient.crawl` 与既有下轮采集边界；未产生“0 条租金”假快照 |
| A8/R8 | 通过 | 限速/冷却/取消复用共享传输层；预算按真实 HTTP 计（自动 5 次/轮，手动 12 次）；过期 revision 409；失败不改旧绑定与人工决定 |

## 4. 复查（check 阶段）发现并修复的问题

复查对象为 commit `8c18f3b` 的文件。修复后重新跑了本文第 2 节的命令，全部通过。

| 问题 | 影响 | 修复 |
|---|---|---|
| 自动绑定把平台地址写进来源的 `address` | 注册表的“同名异址”否决会让位置证据的自动绑定必然失败（地址写法不同即报 `同名异址需要人工确认`）；同一字段还会被 `effective_address`/`admission_address` 当成小区地址证据 | 平台地址改存 `platform_address`，地址与位置证据由本契约判断 |
| 搜索给出的种子未经核验就绑定 | 可能把别的小区的房源挂到本小区，租金统计直接失真 | 自动绑定同样要求详情页 + 同小区列表双重核验（`_verified_seed`） |
| 自动发现每轮重复查同一个小区 | 5 次/轮的预算被首个小区吃光，其余小区永远轮不到 | 用 `rental_xingfuli_auto_cursor` 轮转；预算耗尽的小区保留位置，下一轮优先 |
| `_human_veto` 用 `dict(veto)` 比对来源记录 | 列名不是来源字段，审核锁永远不生效 | 改为按小区审核组（`existing_cid`）判定，并补“来源已有其他有效关联” |
| `select`/`retry` 不检查是否已有任务 | 可同时起两个后台线程写同一份状态 | 运行中一律 409（`ProbeAlreadyRunning`），路由也补了 409 映射 |
| 取消发生在最后一次请求之后仍会落库绑定 | 用户点了取消却仍然绑定 | 绑定前检查取消标志 |
| 搜索阶段遇到冷却被吞掉 | 冷却被报成“未找到主页” | 冷却单独记 `cooling_down` |
| 报告计数按尝试次数而非小区 | 一个小区可被计成多次失败 | 改为按小区计（`checked/matched/pending/missing/failed/deferred`） |
| 探查后无法重新关联被解除的来源 | 人工“解除关联”后该小区永久卡死 | 显式探查视为重新处理，允许再关联（自动发现仍然跳过） |
| `name_conflict` 无调用且语义含混 | 死代码 | 删除，冲突判断统一走 `evaluate` |
| 前端 `busy` 标志在切换小区后不复位 | 新小区的按钮一直禁用 | 无论如何都复位 |
| 前端响应不是 JSON 时抛解析错误 | 用户看到 `Unexpected token <` | 统一成可读提示，并补测试 |

## 5. 未完成 / 已知边界

1. **浏览器端未实测**：桌面与 390px 的探查交互、轮询、取消、重试没有在真实浏览器里点过；只做了静态渲染断言与接口测试。
2. **未跑真实平台上的完整实现链**：烟测是脚本直调适配器，没有走 `ProbeService` 的后台任务再打一次平台（避免重复消耗平台请求额度）。
3. **覆盖率未知**：只测了白金海岸、璞悦湾、东方郡、兴盛花园四个名称样本，不能据此外推 155 个小区的命中率。
4. **自动匹配每小时价**：单轮预算 5 次 HTTP（约 2 个小区/轮），155 个小区需要多轮才能覆盖；这是设计里的既定口径，不是缺陷，但上线后要观察进度。复查后加了轮转游标，覆盖进度不再被首个小区卡住。
5. **生产未部署**：本任务未部署、未写生产关联、未触发生产采集。
6. **前端样式**：`XingfuliProbe` 复用了既有 `rental-source-*` / `btn` 类，没有新增 CSS；视觉细节待真实页面确认。
7. **来源地址展示**：平台地址存在 `platform_address`，目录来源列表的“来源地址”一栏对幸福里来源显示为空（该字段是目录地址口径）；探查候选卡片仍显示平台地址。
