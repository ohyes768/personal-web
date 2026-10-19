# 设计:疑似候选进入 review 队列

## 核心思路

把 `position_one` 的候选收集拆成两层:名称匹配决定**自动绑定资格**,区域内有效 POI 决定**人工可见性**。名称不匹配的 POI 不再静默丢弃,而是带上 `name_matched=False` 标记进入候选列表,排到名称匹配候选之后。

## 后端改动(backend/housing-map/src/services/directory_position.py)

### position_one 候选收集重构

现状:`_name_matches` 内部先 `normalize_poi` 再名称过滤,未匹配的直接丢弃。

改为:`normalize_poi` 只调一次,得到区域内全部有效 POI `valid`,再按名称分两组:

```python
valid = {}                      # source_id -> normalized POI(区域内、分类白名单、非附属设施)
matches = {k: v for k, v in valid.items() if 名称匹配}   # 自动绑定资格
suspects = {k: v for k, v in valid.items() if k not in matches}
```

每个 POI 加 `name_matched` 字段(True/False)。

### 状态分支(关键红线)

```python
if count <= 25 and len(matches) == 1:
    # 自动绑定判断只看名称匹配候选,不看疑似 —— 疑似永不触发 matched
    matched,candidates 仅含该匹配候选(现状不变)
elif matches or suspects or count > 25:
    review,candidates = 匹配 + 疑似
else:
    not_found(不变)
```

**陷阱提示**:如果 matched 分支误用全量候选数判断,单个疑似候选会被自动绑定,违反红线。必须有单测锁死:`单疑似 + count<=25 → review`。

### 排序

review 状态下对全部候选(匹配+疑似)统一计算 `name_similarity` 排序——疑似候选分数天然低,自然排尾。单候选 matched 场景不算分(现状一致)。

### 不改动的部分

- `position_view` / `confirm_position` / `_publish`:candidates 原样透传,`name_matched` 只是新增可选键,旧数据无此字段、前端按缺失=匹配处理,无迁移。
- `confirm_position` 的 `valid_address` 校验已覆盖疑似候选确认路径。
- 事件 `amap_position` 的 state 枚举不变。

## 前端改动(apps/housing-map/src/components/community/PositionPanel.tsx)

1. `PositionPoint` 类型加 `name_matched?: boolean`。
2. 下拉 option 与选中详情行:名称不匹配的候选追加标注(如"名称不匹配,请人工核对")。
3. review + 空候选分支:文案从"暂无可确认的候选位置。"改为引导手动定位:"区内未找到相关地点,结果可能不完整,请使用手动定位确认。"——该分支现在只可能是"count>25 且区内 0 POI"。

## 测试

`tests/test_position_status.py` 新增(mock client):

1. count>25 + 区内 1 个名称不匹配 POI → review,candidates 长度 1,`name_matched=False`(银泰场景)。
2. 单疑似 + count≤25 → review 而非 matched(红线)。
3. count>25 + 区内 0 POI → review + 空 candidates(前端引导文案场景)。

## 回滚

单 commit,`git revert` 即可;无数据迁移、无接口变更。
