# Implement

## 前置

- [ ] 跑 `python -m pytest tests/ -q`(housing-map)确认 name_similarity 基础套件(并行会话产出)全绿
- [ ] `git diff` 查看 amap_directory.py 未提交改动,确认场景 3 不与之冲突

## 步骤

1. [ ] 场景 1:`auction_fetcher` 增加 `fuzzy_community_match`;`normalize_auction` 精确 miss 时走模糊;
       `auction_history.associate_records` legacy 路径同样接入
       → 验证:`pytest tests/test_auction_fetcher.py tests/test_auction_history.py -q`(新增 4 例:精确不变/唯一高分绑/多候选不绑/分期冲突不绑)
2. [ ] 场景 2:`community_auto_review` 两处叠加分数判定
       → 验证:`pytest tests/test_community_auto_review.py -q`(新增:子串不变仍拦/仅高分拦/低分不拦)
3. [ ] 场景 3:高德人工确认候选按分数排序,分数入 evidence
       → 验证:`pytest tests/ -q` 全量;绑定行为不回归
4. [ ] 全量 `pytest tests/ -q` + 后端无 lint 违规
5. [ ] 提交(含 name_similarity 基础套件 + 三个场景 + 本 task 文档),push 前征询

## 回滚点

- 每场景一个 commit;回滚 revert 对应 commit 即可,场景间无依赖。
