# 技术设计：更新管道

## 1. 目标形态

```
routes.py 端点(薄壳 ~5-10 行)
   └─> UpdatePipeline.run(spec, ...)          # 唯一流程实现
          ├─ spec.fetcher()                    # 拉取(各源已有 *Service)
          ├─ spec.validate(df/series)          # 清洗/校验(注册表内声明)
          ├─ DataService.save_xxx(...)         # 落库(复用现有 save 方法)
          └─ spec.build_payload(...) -> *UpdateData   # 响应构造(注册表内声明)
```

## 2. 注册表

`backend/macro/src/services/update_registry.py`：

```python
@dataclass(frozen=True)
class UpdateSpec:
    key: str                          # 如 "us_treasuries"（= CSV section 名）
    endpoint: str                     # "/update/us-treasuries"
    fetcher: Callable[[], UpdateInput]        # 拉取器(复用现有 *Service)
    validate: Callable[[UpdateInput], UpdateInput] | None
    save: Callable[[DataService, UpdateInput], None]
    build_payload: Callable[[UpdateInput], UpdateData]
    failure_is_silent: bool = False   # 对齐现有端点的失败隔离语义
```

- 18 条注册一一对应现有端点；`update_registry.py` 是唯一需要「加数据源」的地方
- 路由文件按域拆分可选（如 routes_update.py），仅当 routes.py 拆分不引发导入环时做

## 3. 兼容策略（关键决策）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 响应 shape | **不变**，各源保留现有 `*UpdateData` | 前端零改动是硬约束；shape 统一收益低风险高，留作后续任务 |
| 联合类型登记 | 不改 Pydantic 模型写法，用**注册表完整性测试**强制 | 动态联合类型伤 IDE/类型检查；测试拦截等价可靠 |
| 失败语义 | 管道内统一 try/except，语义对齐现有端点 | 避免行为漂移；个别端点的特殊隔离逻辑进 spec 声明 |
| save 方法 | 复用 DataService 现有 `save_*`/`append_data` | 落库路径不动，缓存失效逻辑(`_bump_cache_version`)不受影响 |

## 4. 注册表完整性测试（防回归核心）

`tests/test_update_registry.py`：

1. 遍历注册表：每条 spec 的 `build_payload` 返回类型 ∈ `UpdateResponse.data` 联合 → 否则红
2. 反向：`UpdateResponse.data` 联合中每个类型都有注册条目 → 否则红（防死类型）
3. 每条 spec 有对应契约测试存在（按命名约定扫描）→ 否则红
4. endpoint 路径不重复、key 不重复

## 5. 迁移批次（批 2 内部）

按数据源耦合度分 4 小批，每小批迁移后跑全量测试 + 一次 scheduler 手动组触发验证：

1. **FRED 系**：us-treasuries、vix、tga、ted-spread（同源同构，最像，先立模板）
2. **A 股系**：dr007、dr001、volume、turnover、margin
3. **跨源系**：exchange-rates、china-bonds、fund-flow、hibor
4. **收尾系**：commodities、indices、eu-bonds、jp-bonds、遗留 `/update`（971 行旧总端点，评估退役或包一层注册表循环）

## 6. 风险与回滚

- **风险 1**：端点行为漂移（响应字段细节/失败码变化）→ 批 1 契约测试逐字段断言是安全网；迁移前后测试必须全绿
- **风险 2**：scheduler 顺序执行依赖（组内串行）→ 管道不改变端点幂等性，job 配置零改动
- **回滚**：迁移按小批提交，每批独立可 revert；批 2 整体不合入的兜底是保留薄壳前的旧实现分支
