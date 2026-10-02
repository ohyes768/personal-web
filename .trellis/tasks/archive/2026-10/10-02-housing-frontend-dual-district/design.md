# 技术设计：前端双区化

> 依赖子任务 2 已合入的数据：`/api/map/communities` 下发 567 小区（滨江 360 + 萧山 207），
> `district` 字段取值 `滨江`/`萧山`（不带"区"字），萧山 `subdistrict` ∈ {钱江世纪城, 开发区, 宁围, 闻堰}。

## 1. 双围栏常量（src/lib/binjiang-boundary.ts）

- 保留 `BINJIANG_BOUNDARY` + `isInBinjiang`（滨江单区语义不动）。
- 新增 `XIAOSHAN_BORDER_BOUNDARIES: Record<string, [number, number][]>`，与
  `backend/housing-map/src/core/boundary.py` 逐点同步（闻堰 200 / 宁围 100 / 盈丰 34 点，GCJ-02）。
  同步方式：一次性 Python 命令从 boundary.py 生成 TS 字面量粘贴，文件头注释注明来源文件，
  不新增常驻同步脚本（围栏数据静态，变更频率极低）。
- 新增 `isInXiaoshanBorder(lng, lat)`、`isInScope(lng, lat) = isInBinjiang || isInXiaoshanBorder`。
- page.tsx `visiblePOIs` 围栏判断 `isInBinjiang` → `isInScope`（萧山 POI 入图）。

## 2. 区筛选（page.tsx）

- 新增 state `districtFilter: 'all' | '滨江' | '萧山'`（默认 all）。
- `filteredCommunities` 过滤链加 `districtFilter === 'all' || c.district === districtFilter`。
- 地图右侧控制面板顶部新增"区域" chips（全部/滨江/萧山），复用 `poi-toggle` 按钮样式。
- 状态管理沿用现有模式（useState，无 URL query 同步——现状所有筛选均如此，PRD"沿现有筛选状态管理模式"即此意）。

## 3. 默认视野（BinjiangMap.tsx）

- 初始化 `zoom: 13, center: BINJIANG_CENTER` 改为 setBounds 双围栏外接框：
  `SCOPE_BOUNDS`（lng 120.1244–120.3626, lat 30.0994–30.2896）。
- 外接框由 `scopeBounds()` 从围栏集合动态计算（对齐后端 `_scope_bounds()` 模式），改围栏时视野自动跟随。
- 高德类型面补 `AMap.Bounds` 构造器与 `map.setBounds`；setBounds 比手调 zoom/center 精确且跨桌面/移动端自适应。

## 4. 文案

- layout.tsx：title `滨房地图 - 杭州滨江区房价地图` → 双区表述；description 同步。
- types.ts：`Community.district` 注释 `滨江区` → `滨江/萧山`；MOCK_COMMUNITIES 3 处 `'滨江区'` → `'滨江'`（与后端实际值一致，否则区筛选对 mock 失效）。
- page.tsx visiblePOIs 注释"滨江区行政边界"→ 覆盖范围围栏。

## 5. market_reference 看板（降级实现）

后端 `market_reference.json` 是人工校验的安居客快照，scope 仍为 `滨江区`（人工契约，萧山待补录，
见 housing-map-admission.md）。**不虚假标注双区**：

- kicker 已展示 `marketReference.scope`（数据驱动，保留）。
- 硬编码"滨江市场行情 挂牌参考"、"滨江挂牌参考均价"改为中性表述（"挂牌参考行情"、"挂牌参考均价"）。
- 表头区加一行说明：参考行情快照当前仅覆盖滨江区，萧山板块待补录。
- 后端补录萧山后 scope/数据自动生效，前端无需再改。

## 6. 看板区标识与板块筛选

- 板块下拉：硬编码 浦沿/长河/西兴 → optgroup 分组全量 8 板块
  （滨江：浦沿/长河/西兴/**滨盛**——顺带修现状遗漏的滨盛 91 小区；萧山：钱江世纪城/开发区/宁围/闻堰）。
- 表格"板块"列：萧山小区 tag 换 `.tag-xiaoshan` 暖色样式（globals.css 新增，与现有 tag 系列同模式），
  一眼区分两区；滨江小区沿用 `tag-subway`。

## 7. 性能观察（只记录不优化）

build + dev 预览时记录：小区点位 567、轮廓/占位方块数、POI 点位数、看板 50/页分页是否流畅。
结论写入任务归档说明；不流畅再立聚合/分级渲染任务。

## 权衡与不做

- 不加 URL query 同步筛选（现有全部筛选均为 useState，单独给区筛选加 URL 反而不一致）。
- 不新增后端改动（含 scripts/）；围栏 TS 常量一次性粘贴同步。
- 区判定用 `district` 字段而非前端几何判断（后端已按围栏过滤下发，字段即权威）。
