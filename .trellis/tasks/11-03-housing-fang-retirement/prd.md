# 房天下代码与逻辑退役清理

## Goal

退役 housing-map 中的房天下采集能力与旧业务分支，拆分幸福里对旧模块的依赖，减少维护负担。

## Background

2026-11-03 用户明确不再需要来源迁移，旧任务 10-29-housing-rental-source-followup 已关闭归档。用户已要求完成本任务全部规划，本轮不实施。

初步静态盘点：后端运行代码 26 个文件、脚本及说明 4 个文件、前端运行代码 5 个文件、测试 35 个文件包含相关引用；不含单纯的幸福里 /zufang/ 路径。这些是受影响文件数，不是整文件删除清单。

已确认：
- fang_rentals.py、fang_detail_cache.py、fang_request_policy.py 及 scripts/fetch_fang_rentals.py 提供旧采集能力。
- rental_reference/refresh.py 保留 Fang 默认工厂及分支，当前 Web 入口显式使用 xingfuli_only=True。
- directory_collection.py 仍有 fang_names 和 Fang 适配器，目录发现 API 当前仅接受 TMSF。
- xingfuli_rentals.py、xingfuli_transport.py、rental_reference/probe.py、discovery_checkpoint.py 等仍引用旧模块的 RentalCrawlCancelled 或 SeedRunResult，不能直接删除模块。
- 来源管理、快照存储、目录初始化、用途分类、自动审核和前端仍有旧来源兼容逻辑。
- GitNexus 当前无索引；盘点依据为源码及引用检查。

## Requirements

- R1：删除房天下专属采集器、请求策略、详情缓存、采集脚本和失效说明，清除租金与目录流程中的 Fang 网络请求路径及默认工厂分支。
- R2：将幸福里仍使用的取消异常、结果类型等移到公共模块，更新调用方，保持限速、冷却、停止/继续、断点复用与发布行为。
- R3：清理房天下专属 API、前端操作、链接规则、类型分支和无效测试；公共接口的移除或兼容方式在实施设计中明确。
- R4：历史数据默认保留，不删除生产库、关联、快照或人工审核记录；历史 Fang 数据不参与当前来源选择、租金统计及自动用途判定。检查初始化和旧库读取，防止隐式重新导入，禁止将缺少 provider 的旧快照当幸福里。
- R5：更新现行规范及运行说明，移除失效采集指引；历史归档任务与开发日志保留，不要求仓库所有 fang 字符串归零。

## Scope Decisions

- CommunityRegistry 是唯一当前关联权威，不再支持独立 Fang 映射库或 JSON 采集 fallback；旧文件保留但不重新导入，无目录时管理端明确 503。
- 保留当前幸福里使用的来源 GET 与解除接口。旧 search/confirm 保留无副作用的 410 壳，旧 Fang 候选拒绝入口统一 410，不继续保留其数据库或网络实现。
- 当前快照必须显式为 xingfuli 且 neighborhood_id 匹配，缺少 provider 的旧数据不能升级为幸福里；解除幸福里后不回退 Fang。
- 历史人工准入决定与审核记录不改写；停止使用 Fang 参与新的用途判断，不为 Fang-only 未决记录推断住宅，也不改现行 TMSF/高德准入规则。历史来源可只读展示为“房天下（历史）”。
- 通用目录写接口也必须拒绝新关联 Fang；历史读取与显式解绑保留。没有数据迁移或生产操作。

## Acceptance Criteria

- [x] AC1/R1：生产链路无房天下网络请求、采集适配器和默认客户端；记录删除清单与保留项。
- [x] AC2/R2：幸福里生产模块不再导入房天下模块；匹配、探查、采集、取消/恢复、快照发布相关回归通过。
- [x] AC3/R3：前后端无可用房天下采集或来源写入口，退役接口契约明确，幸福里流程及安全链接校验通过。
- [x] AC4/R4：隔离旧库与旧快照验证正常启动、不恢复旧来源、不把旧数据当当前租金、不清空人工决定、不改变住宅准入。
- [x] AC5/R5：相关后端测试和前端 lint、类型检查、测试、生产构建通过；更新规范并记录残留引用用途。

AC1–AC5 的场景、错误语义和逐步验证命令分别见 design.md 的验证矩阵与 implement.md 的步骤 1–7。规划完成不表示这些实施验收已经通过。

## Out of Scope

不实现 Fang→幸福里迁移工具，不清空历史生产数据，不自动部署，不运行生产采集，不扩展数据源，不改变住宅准入规则或当前统计口径。

## Implementation Status

实施已完成（2026-11-03）。AC1–AC5 的证据记录在 verification.md：后端全量 1304 passed / 0 failed，
前端 lint / tsc / 202 项 node --test / 生产构建全部通过，退役端点 410 与 404/503 语义已在重启后的
后端实测，1440px 与窄屏浏览器走查无横向溢出。未实测项（带一次性来源数据的来源弹窗三态、容器构建）
已在 verification.md 如实记录。提交/推送/部署待用户指令。
