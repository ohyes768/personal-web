# 实施计划（仅规划，未开始）

状态保持planning。用户要求本轮创建Trellis任务和规划，未授权开始实现；不得运行task.py start、修改产品代码、部署或写生产绑定。

## 顺序

1. [ ] 前置核对：重新读当前git状态、任务PRD及本任务规范清单；确认现有采集器/目录版本/测试基线，不覆盖共享工作区已有更改。读trellis-before-dev后才编码。
2. [ ] **先过主页发现技术门**：写research/probe-feasibility.md，低频验证名称/别名→平台主页搜索→真实候选页→页内租房入口。特别验证白金海岸总小区ID能否从系统可执行链发现；记录HTTP预算/页面模块身份/失败原因，不使用硬编码样本URL作为发现输入。验证其他小区、分区、错误名称和忽略查询的对照。未通过就保持该项未完成，回报限制并修订设计，不暗自要求粘贴或引入外部搜索商。
3. [ ] 建立脱敏最小fixture与行为回归：自动匹配强证据、推荐噪声、总区/分区、种子与真实ID、主页无入口、入口错归属、取消和旧决定保护。fixture不保存经纪人/图片签名/地图key。
4. [ ] 实现幸福里发现适配，复用请求锁/冷却/取消，按验证结果加入严格搜索及主页路径验证；解析租房搜索、小区搜索、主页租房模块、详情与列表身份。禁止复刻现有采集器。
5. [ ] 实现有版本的probe工作流状态、revision和selected_page；只在证据完整时创建matched来源。新增provider-aware审核能力，预检名称/地址位置，避免现有高相似度分支绕过本任务强证据要求。事务内重查资格、来源唯一性和人工保护。
6. [ ] 接入常规更新，先采已有映射，再按预算自动发现缺来源；保留Fang、现有幸福里优先级及新关联下轮采口径。目录模式取全admitted，旧回退不扩大资格。探查任务和refresh共享租金操作协调，不把网络放在DB事务内。
7. [ ] 接入probe start/status/select/retry/cancel API和持久化恢复；真实HTTP计预算、源独立冷却、重复点击幂等、过期选择409、失败保留selected_page。纯GET不触发发现/写入。
8. [ ] 前端共用探查/主页候选选择组件，管理页和详情一致；移除URL输入和找链接提示。显示进度、位置/分区证据、无主页/无入口/失败/冷却区别，提供重试/取消。绑定后待采集并接既有采集入口。
9. [ ] 隔离DATA_DIR端到端：自动绑定→待采→采集；缺来源→点击探查→候选人工选→系统找入口→绑定；无入口/失败→重试；已有Fang/幸福里不换源。桌面和390px、地图不可用、刷新/后退及重启恢复。
10. [ ] 运行受影响后端/前端检查，逐项验证A1–A8并写verification.md；少量真实公开只读烟测与离线测试分开，不导入生产。更新租金来源/幸福里契约，执行trellis-check后再准备提交或部署评审。

## 文件责任范围（建议）

- backend/housing-map/src/services/xingfuli_discovery.py（新）、xingfuli_rentals.py 请求共用边界。
- backend/housing-map/src/services/rental_reference/probe.py（新）、association.py、providers.py、refresh.py，必要时sources.py/目录coverage投影。
- backend/housing-map/src/api/rental_source_routes.py、rental_routes.py 生命周期/互斥/关闭；CommunityRegistry只做必须的事务扩展，不重写用途/准入。
- apps/housing-map/src/components/rental/RentalAssociationReview.tsx、RentalSourceManager.tsx，共用候选/探查组件和类型/hook；CommunityRentalReference、DirectoryFlowWorkspace按需接线。
- backend/tests新增发现/探查测试及rental系列回归，前端rental-sources/xingfuli/directory-flow/reference相关测试。
- 规范更新：rental-sources.md、xingfuli-rentals.md及受影响覆盖率/租金参考段落。

## 验证命令

先检查当前平台解释器。macOS/Linux在backend/housing-map使用.venv/bin/python；Windows使用.venv/Scripts/python.exe并遵守独立basetemp规范。以下是实施阶段计划，不在规划阶段运行业务测试：

```bash
.venv/bin/python -m pytest tests/test_xingfuli_discovery.py tests/test_rental_probe.py tests/test_xingfuli_rentals.py tests/test_rental_association_flow.py tests/test_rental_providers.py tests/test_rental_refresh.py tests/test_rental_sources.py tests/test_rental_api.py tests/test_directory_flow.py --basetemp=/tmp/housing-xingfuli-source-probe-tests
```

新增文件名在实现时核对后再运行。采集/过滤逻辑有改动时补rental_storage/statistics回归；不要未经改动反复跑全库测试。

在apps/housing-map：

```bash
node --test tests/rental-sources.test.cjs tests/rental-xingfuli.test.cjs tests/rental-reference.test.cjs tests/directory-flow.test.cjs
npx tsc --noEmit
npm run lint
npm run build
```

新增前端工作流测试随实施命名加入。浏览器仅使用隔离HOUSING_DATA_DIR与假上游验证写操作，不对生产制造候选或绑定。

## 验证映射

- A1/A2：真实registry事务、admitted目标、人工保护、拒绝、相似度缺地址及分期/异区负例。
- A3/A4/A6：probe API与桌面/390px交互，单选、无预选、选主页不等于租金来源、无URL表单。
- A5：真实可执行主页发现链记录，不以离线fixture或已知seed代替真实发现。
- A7：provider+真实ID快照隔离、seed独立字段、原统计及下轮采边界。
- A8：复用限速/冷却，实际预算、取消晚响应、重启恢复、过期revision、并发更新/CLI发布时最终写入保护。

## 回退和技术阻塞处理

未通过发现技术门时保留研究和可复现失败，不制造“已完成”记录或扩大外部依赖。上线采用增量meta状态，关闭新发现/按钮即可回退；不清空registry、人工决定或样本。真实全量扫描、部署、生产绑定不在这次规划授权内。

## 规划收敛检查

- [x] 用户目标、范围、无粘贴入口、单选主页后系统继续已确定。
- [x] PRD按最终结构重写，无TBD或待用户回答的产品问题。
- [x] 已检查现有Fang-only审核、幸福里采集器、请求白名单和前端粘贴入口。
- [x] 已给出复杂任务design.md/implement.md及真实上下文清单。
- [x] 技术未知单独落在首道验证门，未伪装成已完成能力。
- [ ] 用户在最终规划摘要之后明确批准开始实现，届时才进入task.py start。
