# 实施清单

## 1. 后端:候选收集重构

- [ ] `backend/housing-map/src/services/directory_position.py` 的 `position_one`:normalize 一次分 `matches` / `suspects`,候选 dict 加 `name_matched` 字段
- [ ] matched 分支判断改为 `len(matches) == 1`(不是全量候选)
- [ ] review 分支 candidates = 匹配 + 疑似,统一 name_similarity 排序

验证:`python -m pytest tests/test_position_status.py -v`

## 2. 后端:新增单测

- [ ] count>25 + 区内名称不匹配 POI → review + 候选含 `name_matched=False`(银泰场景)
- [ ] 单疑似 + count≤25 → review(锁死红线:疑似不自动绑定)
- [ ] count>25 + 区内 0 POI → review + 空候选

验证:`python -m pytest tests/ -v`

## 3. 前端:疑似标注与空候选引导

- [ ] `apps/housing-map/src/components/community/PositionPanel.tsx`:`PositionPoint` 加 `name_matched?: boolean`;option 与详情行标注疑似;review+空候选文案改手动定位引导

验证:`cd apps/housing-map && pnpm lint && pnpm build`

## 4. 全量检查

- [ ] 后端全量测试 + 前端 build 通过
- [ ] 用单测 mock 数据核对银泰场景端到端状态流转(matched/review/not_found 三分支)

## 5. 收尾

- [ ] spec 更新(定位候选规则变更)
- [ ] 单 commit 提交
