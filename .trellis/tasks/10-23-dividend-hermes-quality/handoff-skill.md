# Handoff：开发 dividend-quality-scoring skill（五维基本面评级）

> 交接文档。接手会话读这一份即可独立完成 skill 的开发、发布与冒烟验证，不需要翻完整规划。
> 上游规划：本目录 `prd.md` / `design.md`；本任务总入口。

## 一句话背景

选股关注已用规则筛出 eligible 股票；下一步对它们做 AI 基本面评级。链路：后端把一只股票的财务数据 + 本 skill 的名字发给 NAS 上的 Hermes，Hermes 里的 AI **按本 skill 定死的五维标准**（业务模式/护城河/行业前景/管理层/财务质量）打分、机械映射星级（1-5 星），并生成完整 markdown 基本面说明，只吐回一个 JSON。

**本 skill 是纯提示词工程：一个 SKILL.md 文件，无脚本、无 references**。它必须先把「输入字段、五维细则、判别问题、星级映射、输出 JSON」全部定死，因为后端解析代码（design.md 的 `QualityScore` pydantic）要与它逐字对齐——**skill 契约一改，后端跟着改**。

## 交付物

| # | 产物 | 位置 |
|---|---|---|
| 1 | SKILL.md（五维版，本附二已给全文，微调即可用） | `backend/dividend-select/skills/dividend-quality-scoring/SKILL.md`（仓库内版本化源） |
| 2 | 发布 | 复制到 NAS skills 源目录 → skill-manager 管理台安装到 hermes profile `ohyes768` |
| 3 | 冒烟验证记录 | 本目录 `notes.md` 追加（试跑的股票、返回 JSON、是否合格） |

## 附一：开发要点（为什么这么设计）

1. **五维加权，星级对外**（移植 basic-quality-rating v2.1）
   - business 业务模式 25%：判别问题（复购周期/必需性、定价权、周期敏感度）
   - moat 护城河 25%：五类清单（品牌定价权/转换成本/网络效应/规模/技术与牌照）
   - industry 行业前景 20%：判别问题（5-10 年需求、替代风险）
   - management 管理层 15%：判别问题（决策记录/资本配置/股东一致性/透明度/接班）
   - financial 财务质量 15%：**按输入 payload 硬数据机械核对**（ROE 水平与趋势、毛利率、负债率、扣非同比），金融股替代规则
2. **证据来源分层**：A-D 四维联网搜证（先答判别问题、引用具体事实再打分，禁止凭印象）；E 维只用输入数据核对，不引入外部财务数据。来源优先级：年报/公告 > 券商研报 > 财经数据平台 > 媒体。
3. **星级映射唯一**：weighted_score → stars 机械换算，AI 不许自由发挥。总分不对外展示（序数加权的虚假精度），对外只有五维分项 + 星级 + 边界标注。
4. **边界必标**：距档位边界 < 0.25 时输出 boundary 字段（说明哪一维 ±1 分会跳档）。
5. **缺数据不猜**：payload 字段 null 或搜证查不到 → 对应维度降档，缺口写进 watch_points，禁止编造。
6. **不定价、不荐股**：输出的是「经营质量」评估，明确禁止目标价/买卖建议。

## 附二：SKILL.md 全文（复制后微调）

```markdown
---
name: dividend-quality-scoring
description: A 股公司五维基本面评级（业务模式/护城河/行业前景/管理层/财务质量，各 1-5 分加权，机械映射 1-5 星）。输入一只股票的结构化财务数据 JSON，财务质量维度按输入数据机械核对，其余四维联网搜证后按判别问题打分。最终回复只输出一个评级结果 JSON 对象（含五维分项、星级、边界标注、风险关注点与完整 markdown 基本面报告），不输出其他文本。用于高股息选股筛选后的批量质量评估，不做估值定价与买卖建议。
---

# 五维基本面评级

对输入的单只候选股做基本面评级。评分标准完全固定：**财务质量维度按输入数据逐项机械核对；其余四维联网搜证、先回答判别问题再打分（理由先行，禁止凭印象）**；星级由加权总分机械映射。不编造缺失数值，不给估值与买卖建议。

## 输入

调用方在 prompt 中提供一只股票的 JSON 对象，字段：

| 字段 | 含义 | 缺失处理 |
|---|---|---|
| code / name | 代码 / 名称 | 必有 |
| sw_level1 / sw_level2 | 申万行业 | 可 null，行业判断用搜证结果 |
| yield_2023/2024/2025 | 各年股息率(%) | 可 null |
| avg_yield_3y | 3 年平均股息率(%) | 必有 |
| dividend_count_2023/2024/2025 | 各年分红次数 | 可 null |
| payout_ratio | 分红比例(%) | 可 null |
| roe / roe_year | 最近年度加权 ROE(%) 与年度 | 可 null |
| roe_avg_3y / roe_history | 3 年平均 ROE 与历年 [{year,value}] | 可 null |
| annual_net_profit_ex_non_recurring / annual_profit_year | 年度扣非净利润(元) 与年度 | 可 null |
| net_profit_ex_non_recurring_yoy | 年度扣非同比(%) | 可 null |
| net_profit_cagr_3y | 扣非 3 年复合增速(%) | 可 null |
| previous_quarter_yoy_pct / previous_quarter_label | 上一季单季扣非同比(%) 与报告期 | 可 null |
| latest_quarter_yoy_pct / latest_quarter_label | 最新季单季扣非同比(%) 与报告期 | 可 null |
| debt_asset_ratio | 资产负债率(%) | 可 null |
| gross_profit_margin | 毛利率(%) | 可 null |
| shareholder_count / shareholder_change_pct | 股东户数 / 增幅(%) | 可 null，仅参考 |
| eps / eps_year | 摊薄 EPS(元) 与年度 | 可 null |

任何字段为 null：对应细则内降档，并把「XX 数据缺失」写入 watch_points。

## 五维评分（每维 1-5 分，先理由后分数）

### A. business 业务模式（权重 25%）

联网搜证。先回答判别问题，引用具体事实：
1. 客户多久买一次？不买行不行（必需 vs 可选）？
2. 它敢不敢涨价？涨价会不会丢客户（定价权）？
3. 收入靠量还是靠价？周期下行收入会不会大幅下滑？

| 分 | 标准 |
|---|---|
| 5 | 必需品 + 高复购 + 强定价权（提价不丢量） |
| 4 | 必需品偶尔消费 OR 高端可选消费 + 强品牌 |
| 3 | 周期品 + 长期需求 OR 品牌消费品增长见顶 |
| 2 | 周期品 + 替代风险 OR 多元不相关业务 |
| 1 | 强周期 + 政策风险 + 商业模式脆弱 |

### B. moat 护城河（权重 25%）

联网搜证，逐项核对五类护城河（品牌/定价权、转换成本、网络效应、规模效应、技术与牌照），每项判断强弱并给证据：

| 分 | 标准 |
|---|---|
| 5 | 4 项以上强护城河 |
| 4 | 3 项强护城河 |
| 3 | 2 项中等护城河 |
| 2 | 1 项弱护城河 |
| 1 | 几乎无护城河 |

### C. industry 行业前景（权重 20%）

联网搜证。判别问题：5-10 年后行业总需求比今天多还是少、驱动因素是什么；有没有技术/政策/替代品正在侵蚀。

| 分 | 标准 |
|---|---|
| 5 | 老龄化/全球化/数字化等长期红利驱动 |
| 4 | 结构性增长 + 政策支持 |
| 3 | 成熟稳态 + 高端化转型 |
| 2 | 行业见顶 + 替代风险 |
| 1 | 夕阳行业 + 政策风险 |

### D. management 管理层（权重 15%）

联网搜证。判别问题：近 5 年关键决策记录（并购成败/跨界）；资本配置（钱花在产生回报的地方吗）；股东一致性（增持/回购/分红 vs 减持）；信息披露透明度；接班风险。

| 分 | 标准 |
|---|---|
| 5 | 顶级 + 长期主义 + 股东友好（增持/高分红/回购） |
| 4 | 优秀 + 透明 + 长期记录良好 |
| 3 | 一般 + 无重大问题 |
| 2 | 激励不足 + 信息披露弱 OR 有争议决策 |
| 1 | 治理风险 + 重大负面历史 |

### E. financial 财务质量（权重 15%）——只用输入数据机械核对，不引入外部财务数据

容忍行业 = 银行/非银金融/公用事业/交通运输（负债率阈值上调一档）。

先核对四项：
1. ROE 水平：roe_avg_3y（并参考 roe）——≥15% 优；12-15% 良；8-12% 中；5-8% 弱；<5% 差
2. ROE 趋势：roe_history——逐年稳定或上行 优；1 年下滑 良；连续下滑 弱
3. 负债率 debt_asset_ratio：≤40% 优（容忍 ≤55%）；40-60% 良（容忍 ≤70%）；60-75% 中（容忍 60-80%）；>75%（容忍 >80%）差
4. 盈利趋势：net_profit_ex_non_recurring_yoy 与最近两季单季同比——均为正 优；单季为负 良偏下；连续两季为负 弱

合成规则：
| 分 | 标准 |
|---|---|
| 5 | ROE 优 且 负债率优 且 盈利趋势优 |
| 4 | ROE 良及以上，仅一项次指标为良 |
| 3 | ROE 中；或 ROE 良但两项次指标弱 |
| 2 | ROE 弱 OR 负债率差 OR 盈利趋势弱 |
| 1 | ROE 差 OR 两项以上不达标 |

毛利率参考：≥40% 加分项（可弥补单项良→优）；高周转模式（毛利率 <20% 但 ROE 优）不因低毛利率扣分。
roe_avg_3y 为 null 时该维度不得高于 3，并记 watch_point。
金融股（银行/保险）：负债率维度跳过，改看不良与资本充足水平的搜证结果；不得因高杠杆扣分。

## 加权与星级（机械换算，唯一）

weighted_score = business×0.25 + moat×0.25 + industry×0.20 + management×0.15 + financial×0.15（保留两位小数）

| weighted_score | stars |
|---|---|
| ≥ 4.5 | 5 |
| 4.0-4.5 | 4 |
| 3.0-4.0 | 3 |
| 2.0-3.0 | 2 |
| < 2.0 | 1 |

边界规则：weighted_score 距上下档位边界 < 0.25 时，boundary 填「{维度中文名} {分数}→{±1} 即{升/降}至{N}星」（选权重最大的可跳档维度），否则为 null。

## 数据来源优先级（A-D 搜证适用）

公司年报/公告 > 券商研报 > 财经数据平台 > 媒体报道。引用媒体级来源须在理由中标注「媒体来源」。

## 输出（最终回复只含此 JSON，裸 JSON，无 markdown 围栏、无解释文字）

{"code": "<输入 code>", "name": "<输入 name>",
 "dimensions": {"business": <1-5>, "moat": <1-5>, "industry": <1-5>, "management": <1-5>, "financial": <1-5>},
 "weighted_score": <加权总分，两位小数>,
 "stars": <1-5>,
 "boundary": "<边界说明或 null>",
 "summary": "<一句话结论：作为长期持有的基本面质量如何，最有力的依据>",
 "risks": ["<最关键 1-3 条风险，须能从输入或搜证事实推出>"],
 "watch_points": ["<数据缺口与需下次复核的点>"],
 "report_md": "<完整 markdown 基本面报告，模板见下>"}

### report_md 模板（字符串内换行用 \n）

# 基本面评级：{name}（{code}）

评级日期：{今天日期} · 星级：{"⭐"×stars}

## 业务核实
{1-2 句主营业务定义}

## 五维评分
| 维度 | 分 | 理由 |
|---|---|---|
| 业务模式 | {1-5} | {引用事实/数据，1-2 句} |
| 护城河 | {1-5} | {哪些护城河 + 证据} |
| 行业前景 | {1-5} | {趋势判断 + 依据} |
| 管理层 | {1-5} | {关键事实} |
| 财务质量 | {1-5} | {ROE/负债率/扣非同比 具体数值} |

## 星级与边界
⭐{星级}（{stars}/5）{边界说明或"非边界档位"}

## 结论与风险
{summary 展开 2-3 句}

**主要风险**：{risks 逐条}
**关注点**：{watch_points 逐条，无则写"无"}

summary/risks/watch_points/report_md 用简体中文，具体、引用数值。
禁止输出：目标价、买卖建议、输入之外的事实推测（搜证结论须注明来源等级）。
```

## 发布步骤（操作，非代码）

1. 把 `backend/dividend-select/skills/dividend-quality-scoring/SKILL.md` 复制到 NAS skills 源仓库（本机 `.env` 的 `SKILLS_SOURCE_HOST_PATH` 指向的路径）对应目录。
2. 打开 skill-manager 管理台（nginx 路径 `/skills`），刷新源目录 → 新建/识别该 skill → 安装到 hermes profile `ohyes768`。
3. 确认安装状态为成功（管理台显示该 skill 已安装到目标 profile）。

## 冒烟验证（发布后在 Hermes 上手工试跑）

1. 从 `GET /api/dividend/stocks/{code}`（本机或 NAS 8092）取一只 eligible 股票，按附二字段表手工拼一个 JSON（字段名保持一致）。
2. 提交 run（Bearer key 取 NAS 上 hermes 的 key）：

```bash
curl -X POST "http://<nas>:8642/p/ohyes768/v1/runs" \
  -H "Authorization: Bearer <HERMES_API_KEY>" \
  -H "Idempotency-Key: smoke-quality-600900-1" \
  -H "Content-Type: application/json" \
  -d '{"input": "请使用 dividend-quality-scoring skill 评估以下股票，按 skill 输出契约只回复 JSON：{...股票JSON...}"}'
```

3. 轮询 `GET http://<nas>:8642/p/ohyes768/v1/runs/<run_id>`（同 Bearer），到 `completed` 后取 `output`。
4. 合格标准：
   - output 是合法 JSON，字段与附二输出契约完全一致（code/name/dimensions 五键/weighted_score/stars/boundary/summary/risks/watch_points/report_md）
   - weighted_score = 加权和（±0.01）；stars 与映射表一致；boundary 在边界距离内非空
   - dimensions 分数均在 1-5；report_md 非空且含五维评分表
   - E 维理由中的数值能在输入里找到出处；A-D 理由含具体事实而非空泛形容
   - 换 2-3 只不同特征的股票（如高股息银行 / 公用事业 / 一只有单季下滑的）各跑一次，同一股票重跑两次星级一致（允许 boundary 内 ±1 维分波动，星级不变）
5. 结果（股票、run_id、JSON 摘要、是否合格）记入本目录 `notes.md`。不合格则改 SKILL.md 细则重发布再试。

## 验收清单

- [ ] SKILL.md（五维版）已入仓 `backend/dividend-select/skills/dividend-quality-scoring/`
- [ ] 已发布到 hermes profile，管理台显示安装成功
- [ ] ≥3 只股票冒烟通过，同一股票重复跑星级一致
- [ ] `notes.md` 有冒烟记录
- [ ] 与后端契约对齐确认：字段名、维度 key（business/moat/industry/management/financial）、星级 1-5 与 `design.md` 的 `QualityScore` 一致（后端开发前置条件）
