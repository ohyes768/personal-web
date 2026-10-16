# housing-map 数据链路整理

> 2026-10-16 梳理,基于当前工作区代码。滨江购房地图后端 `backend/housing-map`,前端 `apps/housing-map`。

## 总览

整个系统围绕 SQLite `data/community_registry.sqlite3` 的三张表展开:

- `communities` — 小区主档(payload JSON)
- `sources` — 外部来源记录(TMSF/高德/租金/法拍),通过 `cid` 关联主档
- `community_admission` — 收录判定(state / reason / rule_version)

数据流:**透明售房网出名单 → 高德出坐标 → 房天下出租金 → 法拍网站出法拍记录 → 地图汇总画图**。

除了透明售房网价格刷新有 cron(`scheduler.py:36`),其余采集全部手动触发,入口集中在管理页。

### 贯穿性共享机制:name_similarity

[name_similarity.py](../backend/housing-map/src/services/name_similarity.py):

- 流程:NFKC 归一 → 剥通用后缀(花园/苑/府等)→ RapidFuzz ratio / JaroWinkler / partial_ratio / 拼音四者取最大
- 分期不同(一期/二期)直接 0 分
- `AUTO_THRESHOLD = 0.92`
- 原则:**唯一候选 + 相似度过线才自动绑;并列或低分一律留人工**。docstring 明确"相似度是证据,永远不是唯一裁决"

该模块从各链路抽取后已被三处复用:采集自动关联、租金绑定、法拍绑定。

---

## 1. 透明售房网采集 → 收录/未收录

### 采集

- 拉取 TMSF 的 JS 索引 `index_search_newCommunitylist.js`,解析小区数组;范围硬编码滨江全区 + 萧山接壤 4 板块(钱江世纪城/开发区/宁围/闻堰)(`scripts/fetch_tmsf_binjiang_communities.py`)
- 逐小区抓详情页补物业类型/地址/挂牌数;失败走新房项目索引兜底(`tmsf_property_type.py:42`)
- HTTP 用 curl_cffi Chrome 指纹(`tmsf_fetcher.py:53-105`)
- 触发:管理页 `POST /api/directory/collection`,后台线程跑,`DELETE` 可取消;无定时任务

### 收录规则(directory_policy.py,rule_version='tmsf-directory-v1')

逐条否决,全部通过才 admitted:

| 否决原因 | 条件 |
|---------|------|
| 物业类型 | 必须 ∈ {住宅、别墅、排屋};明确非住宅(写字楼/商贸/车位)排除;"公寓"等模糊类型 → `type_uncertain` 暂不收录 |
| 地址 | 缺失/待核实 → `address_missing` |
| 挂牌量 | 不过门槛 → `listing_gate` |
| 身份 | 删除/合并 → inactive;人工排除/锁 → manual_exclusion;名称与身份冲突 → identity_conflict |

### 自动去重(两层)

1. **关联已有主档**(`community_registry.py:270` auto_associate):normalized 精确名匹配唯一 → 自动关联;仅子串相似的唯一候选需相似度 ≥0.92,否则留待审;同名异址拒绝自动
2. **建新主档**(`directory_workflow.py:24` materialize):eligibility 通过且名称+区域与所有现有主档精确无重合 → 自动建 admitted;有重合保持 pending

### 人工介入

directory 模式下人工 admit 已封死("住宅名单已改为透明售房网自动分类"),收录全自动;人工只剩异常记录补资料。

---

## 2. 高德定位补 POI + 住宅分类

### 搜索(amap_directory.py)

- 高德 V3 关键词搜索 `place/text`,`city=杭州&citylimit=true&types=120300|120203`
- 搜索词 = 小区主名,无命中且未截断时依次用前 3 个别名重试(`directory_position.py:143-155`)

### 候选过滤

- 区域限滨江/萧山且 adname 匹配
- 分类码白名单:**120300 住宅区及子类(120301-120304)+ 120203 商住两用楼宇**(复合码任一段命中即可)
  - 120203 为后续纳入:TMSF 住宅项目(公馆/公寓)在高德常落在商住分类下,不加会漏定位
- 剔除附属 POI:出入口/停车场/售楼处/东西南北门/N 幢
- 名称用"拉平名"比对(去括号/间隔号/通用后缀,相等或短侧 ≥3 字包含即命中)
- GCJ02 坐标 + 行政边界校验

### 分类器分层

- 高德分类码只用于 POI 过滤(发现线索,不作住宅用途证据)
- `residential_classifier.py` 是跨源用途分类:TMSF 类型 住宅/别墅/排屋 = residential,写字楼/商贸/车位 = non_residential,公寓/其他 → pending

### 自动绑定与人工确认

- **未截断(count≤25)且唯一候选 → 自动绑 matched**(即使包含命中、地址不同)
- 多候选或截断 → `review` 进人工队列
- 状态机六态:pending / matched / review / not_found / error / manual;批量任务只处理 pending/error,已 matched 不回退
- 人工确认 `POST /catalog/{cid}/position/confirm`:从候选选 POI(须有有效地址)或手填经纬度+地址,写入后 state=manual;带 revision 防并发

### 绑定后存储

写 `communities.payload`:`amap_position`(state/selected/candidates/时间戳);若无既有图上点位则补 `longitude/latitude/coordinate_system=gcj02` + `geographic_address` + `coordinate_evidence`(source='amap'|'manual')。

---

## 3. 租金采集 → 相似度自动绑定

### 采集(fang_rentals.py + rental_reference/)

- 唯一来源:**房天下杭州租房**(`zu.fang.com`),curl_cffi 伪装 Chrome
- 遍历已收录小区(eligible:滨江 + 住宅 + 挂牌门槛),搜索词拼 `{BASE_URL}/hz/house/kw{name}/`
- 校验页面条件栏回显关键词必须等于搜索词,防止全市推荐房源污染;空结果换别名重试一次
- 触发:`POST /rentals/refresh` 单槽后台任务;先来源发现/绑定,再对已绑定小区逐个爬列表页(默认 10 页、间隔 2s)

### 自动绑定

复用 name_similarity:精确唯一 → 绑;否则唯一候选且 ≥0.92 → 绑,证据记"唯一候选,名称相似度 x.xx"。无区域/地址硬条件,地址只作人工核对证据。

### 人工判断

不能自动绑的按原因落:

- `needs_selection`(多候选或低分)
- `missing`(搜不到)
- `search_failed` / `deferred`

入口:管理页**"租金来源待处理"独立标签页**(a1c121e 拆出),`GET/POST /rentals/association-tasks`,人工 bind/skip/reopen;与刷新互斥。另有单小区手动搜索/确认接口。

### 存储与统计

- 绑定关系存 registry `sources` 表;房源样本按 run 写 `runs/<run_id>/batch.json`,`current.json` 指针原子切换;失败小区沿用旧数据或缺席
- 统计(`statistics.py`):全量过筛(排除合租/疑隔断/非住宅/未抓详情等)→ 按面积段(<90/90-144/≥144㎡)× 室数分组,**每组 ≥3 条才出参考值** → 中位数月租/单价 + P25/P75
- 快照超 30 天过期;收益率 = 单位月租 × 12 / 售单价

---

## 4. 法拍采集 → 自动/人工绑定

### 采集(auction_fetcher.py)

- 来源:第三方聚合"来拍严选"API(faeping.com,非阿里/京东直连)
- 按 province=330000 / city=330100 / 住宅类翻页,只保留 **area_code=330108(滨江)住宅**;跳过已 ignore 的 identity
- 字段:标题/地址/轮次、起拍/评估/成交价、建筑面积(三级来源:结构化 → 调查表 → 公告正则)、法院、平台、腾空/租赁/过户/税费风险标签(长数字脱敏)
- 触发:手动 `POST /api/auctions/refresh`;无定时任务

### 自动绑定

1. 唯一精确名匹配(community_name/alias/aliases 建索引)→ 绑
2. 模糊兜底:唯一候选且相似度 ≥0.92 → 绑;并列或低分不自动选

### 人工绑定

绑不上的进 registry pending,按原因分 4 类(身份冲突/无候选/多候选/证据不足)。入口:

- 列表 `GET /api/auctions/associations/pending`
- 人工操作 `POST /api/directory/sources/{rid}/associate`(绑已有小区)/ `create-community`(建新)/ ignore

### auction_history(查询时关联)

- 不写原始数据:读 auction_records.json → 经 registry matched 映射关联小区 → 按房源聚合多轮拍卖 → 只取最新一次**有成交价的成交**(status=done)
- 支持期间(12m/24m/all)与面积段过滤,输出单价中位/最小/最大
- 绑定关系修订后老记录无需重采即生效

---

## 5. 地图首页画图(apps/housing-map)

高德 JS API 2.0,basePath `/map`,唯一页面 `src/app/page.tsx`,`/api/*` rewrite 到后端 :8096。

| 图层 | 数据来源 | 说明 |
|------|---------|------|
| 小区轮廓(主图层) | `GET /api/map/communities` | 多边形按价格五档色阶(绿 <2万 → 红 >7万,无价灰);只画 OSM 来源轮廓 |
| 定位占位 | 同上 | 有定位无轮廓 → 100m×100m 虚线方块 + "?";无经纬度 → 不画 |
| POI 点 | communities 内嵌 pois | 地铁/学校/医院/商场/公园,滨江围栏过滤 + 跨小区去重 + 学段筛选 |
| 地铁线路 | `GET /api/map/transit` | OSM 数据 |
| 法拍 | community-summary + auction-history | 不画独立图层;悬停徽标"历史法拍 N 套",弹窗内最近成交卡 |
| 租金 | `GET /api/map/communities/{id}/rentals` | 弹窗"租金与收益"tab:月租中位数/P25-P75/年化收益率/逐条样本 |

交互:点击轮廓弹窗(挂牌/签约均价、法拍卡、2×2 评分卡、1500m 配套半径圈);筛选器:名称/区域/POI 图层/价格口径(混合/仅签约/仅挂牌)/物业类型(默认仅住宅/别墅/排屋)。

---

## 一句话总结

TMSF 全自动收录 → 高德定位(多候选人工挑)→ 租金与法拍做相似度绑定(0.92 阈值 + 唯一候选原则,绑不上的人工兜底)→ 前端拿定位 + 轮廓 + 价格画图,法拍和租金在弹窗里看。

系统灵魂:**机器只在非常有把握时自动操作,没把握就老实等人确认——宁可多让人点几下,不许绑错。**
