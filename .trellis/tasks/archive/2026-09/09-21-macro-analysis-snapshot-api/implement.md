# 实施计划：宏观 Skill 聚合快照 API

1. 在 `tests/test_analysis_snapshot.py` 写失败测试，使用 fake monthly/daily service 验证七卡投影、双月顺序、默认期、无效参数与缺失期。
2. 在 `src/models.py` 定义专用 Pydantic 响应模型；在 `src/services/analysis_snapshot_service.py` 实现聚合与质量计算。
3. 在 `src/api/routes.py` 接入 `GET /analysis/snapshot`，复用服务并返回模型。
4. 运行目标 pytest；再运行月度、日频回归测试。
5. 在 `backend/macro/docs/ANALYSIS_SNAPSHOT_API.md` 写公开 API 文档，并在文档索引登记。
6. 核对 OpenAPI 路径、七卡 key 清单与旧接口兼容性。

## Validation

```powershell
python -m pytest tests/test_analysis_snapshot.py -q
python -m pytest tests/test_daily_snapshot.py tests/test_macro_signal_month_avg.py -q
```
