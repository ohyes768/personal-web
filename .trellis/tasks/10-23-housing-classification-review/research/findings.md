# 调研结论（2026-10-23）

## 需求来源
codex 会话 01a16689-f70（2026-10-23 02:14）与用户确认的完整方案。起因：风雅钱塘世纪花园（TMSF id 10001039）被透明售房网标「商贸」导致不收录，克而瑞（住宅）/房天下（普通住宅）/高德（住宅小区 120302）三方均表明为住宅。用户确认主流程：透明售房网采集 → 高德匹配并复核分类 → 分流已收录/未收录/待审核。

## 用户拍板的决策矩阵
| 透明售房网分类 | 高德分类 | 处理结果 |
|---|---|---|
| 住宅 | 住宅小区 | 已收录 |
| 明确非住宅 | 明确非住宅 | 未收录，保留原因 |
| 住宅 | 明确非住宅 | 待审核：分类冲突 |
| 明确非住宅 | 住宅小区 | 待审核：分类冲突 |
| 任一方分类不明、商住混合 | 任意 | 待审核：用途待确认 |
| 高德未找到、匹配不确定 | 任意 | 待审核：关联待确认 |

补充规则（用户确认）：
- 查询失败/未找到 ≠ 复核不通过，保留待复核可重试，不得据此判非住宅。
- 已收录仍需满足区域、地址、挂牌数量等既有条件，分类复核只是其中一关。
- 人工审核结果独立保存，采集刷新不覆盖；出现新的相反证据时提示复审。
- 高德结果只标记「疑似住宅/存在冲突」，不自动放行；收录/排除只能人工确认。

## 来源选型结论（NAS 实测）
| 来源 | 单次耗时 | 分类 | 批量能力 |
|---|---|---|---|
| 高德 POI 搜索 | ~0.12s | 住宅小区（typecode） | 正规 API，个人认证约 5000 次/月 |
| 克而瑞 | ~0.33s | 物业类型：住宅 | 无免费批量 API，已知 ID 可读详情 |
| 房天下 | ~0.66s | 普通住宅 | 有风控（滑块）问题 |

结论：高德做批量复核筛查；克而瑞/房天下作为人工确认阶段的证据链接，本轮不自动采集。

## 现有代码落点
- `backend/housing-map/src/services/directory_policy.py` — `eligibility()` 纯函数；TMSF 类型 `<= NON_RESIDENTIAL_TYPES` 直接 `non_residential` 不收录（风雅钱塘案例根因）；`property_type_conflict` → incomplete。
- `backend/housing-map/src/services/community_registry.py:90-92` — 目录模式（`tmsf-directory-v1`）下手动 admit 被禁止（「住宅名单按透明售房网资料自动分类，不能手工绕过条件」），当前无任何人工纠错出口。
- `backend/housing-map/src/services/residential_classifier.py:118-120` — `classify_sources` 刻意跳过 amap 来源（"Map categories are a discovery hint, not legal residential-use evidence"）。
- `backend/housing-map/src/services/directory_position.py` + `directory_position_state.py` — 定位批量任务模式：身份指纹、快照、256 请求预算、2s 间隔、取消/原子发布、`amap_position` 附加 payload。**不存 typecode**。
- `backend/housing-map/src/services/amap_directory.py` — `AmapClient.search_name` 搜索**限定** `types=120300|120203`（住宅白名单），所以现有定位关联只能证明「住宅类」，永远发现不了「高德说非住宅」方向 → 复核需要不限类型的独立查询。`normalize_poi` 白名单 {120300,120301,120302,120303,120304,120203}，复合 typecode 用 `|` 分段。名称拉平/别名/包含匹配规则在 directory-position spec 有完整契约。
- `backend/housing-map/src/services/community_admission.py:142-147` — directory_mode 下 `classify_sources` 只喂 tmsf 记录；非人工 admitted 遇新冲突证据会投影回 pending（复审降级已有先例）。
- 旧 amap 发现来源（`source='amap'`, `source_kind='poi'`）payload 里有 `poi_typecode`，但仅限住宅白名单内的 POI。

## 受影响的既有契约（Phase 3 需更新 spec）
- `directory-flow.md`：「Fang rental types, Amap categories and auction titles never admit/veto residential use」需改写为：高德分类可制造待审核冲突、支撑人工确认，但仍永不自动收录/排除。
- `directory-flow.md`：「Excluded … has retry, no manual-use confirmation」需改为受控的用途人工确认入口。
- `directory-position.md`：定位与用途复核共用名称匹配规则但查询互相独立的边界说明。
