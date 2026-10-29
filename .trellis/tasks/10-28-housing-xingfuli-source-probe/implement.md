# 实施计划（已实施）

状态：in_progress（2026-10-29 用户批准后启动）。技术门已通过，结论回写 `design.md`，证据见 `research/probe-feasibility.md`，
验证记录见 `verification.md`。

## 顺序

1. [x] 前置核对：重新读当前git状态、任务PRD及本任务规范清单；确认现有采集器/目录版本/测试基线，不覆盖共享工作区已有更改。读trellis-before-dev后才编码。
2. [x] **先过主页发现技术门**：写research/probe-feasibility.md，低频验证名称/别名→平台主页搜索→真实候选页→页内租房入口。已验证：平台内多通道搜索可发现总小区，不需要外部搜索；`design.md` 已按实测修正。
3. [x] 建立脱敏最小fixture与行为回归：`tests/test_xingfuli_discovery.py`、`test_rental_probe.py`、`test_rental_xingfuli_sources.py`，覆盖强证据、噪声、分区、种子与真实ID、主页无入口、入口错归属、取消与旧决定保护。
4. [x] 实现幸福里发现适配：抽出 `xingfuli_transport.py` 共享限速/冷却/取消；`xingfuli_discovery.py` 负责搜索、主页解析、详情与列表归属核验。
5. [x] 实现带版本与 revision 的 probe 工作流状态（`rental_probe:{cid}`）、selected_page 与只在证据完整时创建 matched 来源；人工保护在写入前重查。
6. [x] 接入常规更新：`RentalRefreshService(auto_discover=True)` 在采集后按预算自动发现缺来源小区；默认关闭以便离线运行与回退。
7. [x] 接入 probe start/status/select/retry/cancel API与持久化状态；真实HTTP计预算、重复点击幂等、过期选择409、失败保留selected_page；纯GET不触发发现。
8. [x] 前端共用 `XingfuliProbe` 组件，管理页与详情一致；移除URL输入与找链接提示；区分无主页/无入口/失败/冷却并提供重试与取消。
9. [~] 隔离DATA_DIR端到端：接口级与组件级已覆盖；**浏览器桌面/390px 实测未做**（见 verification.md 第4节）。
10. [x] 运行受影响后端/前端检查，逐项核对A1–A8并写 `verification.md`；真实公开只读烟测与离线测试分开，未导入生产。已新增 `xingfuli-discovery.md` 契约并更新租金来源/幸福里契约。

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
