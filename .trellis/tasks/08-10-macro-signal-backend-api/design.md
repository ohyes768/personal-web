# Design — global-macro-fin /api/macro/signal 接口

## 1. 模块文件改动(在 `backend/global-macro-fin` 子模块内)

```
backend/global-macro-fin/
├── src/
│   ├── api/routes.py                         # 修改: 加 2 个接口
│   ├── config.py                             # 修改: 加 macro_signal_data_dir 配置项
│   ├── models.py                             # 修改: 加 MacroSignal 相关 Pydantic 模型
│   └── services/
│       └── macro_signal_service.py           # 新增: 读 JSON + 聚合 + 缓存
└── docs/
    └── MACRO_SIGNAL_API.md                   # 新增: 接口文档(给后续 agent 用)
```

## 2. 数据契约(对齐前端 `MacroSignalSnapshot`)

```typescript
// 前端 types.ts 已有,后端用 Pydantic 镜像:
{
  "month": "2026-05",
  "generated_at": "2026-05-22T07:28:47Z",   // 可选
  "groups": {
    "monetary_policy": {
      "conclusion": "偏宽松",                // str | null
      "indicators": [
        { "key": "dr007",  "value": 1.328, "updated_at": "2026-05-21" },
        { "key": "lpr_1y", "value": 3.0,   "updated_at": "2026-05-21" }
      ]
    },
    "money_supply":   { ... },
    "entity_economy": { ... },
    "inflation":      { ... },
    "exchange_rate":  { ... },
    "risk_appetite":  { ... }
  }
}
```

## 3. Pydantic 模型(`src/models.py` 新增)

```python
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MacroIndicator(BaseModel):
    """单个指标(粒度到指标级,updated_at 是 ISO 'YYYY-MM-DD')"""
    key: str
    value: Optional[float] = None
    updated_at: Optional[str] = None  # 'YYYY-MM-DD'


class MacroSignalGroup(BaseModel):
    """一个分组(6 大主题之一)"""
    conclusion: Optional[str] = None
    indicators: List[MacroIndicator] = []


class MacroSignalSnapshot(BaseModel):
    """一个月快照 = 6 个分组"""
    month: str  # 'YYYY-MM'
    groups: Dict[str, MacroSignalGroup]  # 6 个 dimension key
    generated_at: Optional[str] = None


class MacroSignalResponse(BaseModel):
    """GET /api/macro/signal 响应"""
    success: bool = True
    data: MacroSignalSnapshot


class MacroMonthsResponse(BaseModel):
    """GET /api/macro/months 响应"""
    months: List[str]  # 降序


class ErrorResponse(BaseModel):
    detail: str
```

## 4. 配置项(`src/config.py` 新增)

```python
class Settings(BaseSettings):
    # ... 现有配置 ...

    # macro-fin-skill 输出目录(给后端读取各 JSON)
    # 默认本地开发路径,生产环境通过 MACRO_SIGNAL_DATA_DIR 环境变量覆盖
    macro_signal_data_dir: str = "F:/personal-projects/macro-fin-skill/skills"
```

Pydantic Settings 自动从 `MACRO_SIGNAL_DATA_DIR` 环境变量读取(不区分大小写)。

## 5. Service(`src/services/macro_signal_service.py`)

```python
"""宏观信号服务:读 macro-fin-skill 输出的 JSON,聚合成前端需要的 shape"""
import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, List

from src.config import get_settings
from src.models import MacroSignalSnapshot, MacroSignalGroup, MacroIndicator
from src.utils.logger import setup_logger

logger = setup_logger("macro_signal_service")


# 6 个 skill 的 dimension key → JSON 文件名
DIMENSION_FILES = {
    "monetary_policy": "monetary-policy-skill/macro_signal.json",
    "money_supply":    "money-supply-skill/macro_signal.json",
    "entity_economy":  "entity-economy-skill/macro_signal.json",
    "inflation":       "inflation-skill/macro_signal.json",
    "exchange_rate":   "exchange-rate-skill/macro_signal.json",
}

# risk_appetite 是 risk_data.json(不是 macro_signal.json)
RISK_APPETITE_FILE = "risk-appetite-skill/risk_data.json"

# 6 个 dimension 的固定顺序(前端 GROUP_ORDER 对齐)
DIMENSION_ORDER = [
    "monetary_policy", "money_supply", "entity_economy",
    "inflation", "exchange_rate", "risk_appetite",
]


class MacroSignalService:
    """单例服务"""

    def __init__(self):
        self.settings = get_settings()
        self._cache: Dict[str, tuple[float, object]] = {}  # key → (timestamp, value)
        self._cache_ttl = 300  # 5 分钟

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ts, _ = self._cache[key]
        return (time.time() - ts) < self._cache_ttl

    def _get_cached(self, key: str):
        return self._cache[key][1] if self._is_cache_valid(key) else None

    def _set_cache(self, key: str, value):
        self._cache[key] = (time.time(), value)

    def _read_json(self, rel_path: str) -> Optional[dict]:
        """读 skill JSON 文件,容错处理"""
        full_path = Path(self.settings.macro_signal_data_dir) / rel_path
        try:
            with open(full_path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"macro-signal JSON 不存在: {full_path}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"macro-signal JSON 解析失败: {full_path} - {e}")
            return None

    def _convert_dimension_from_macro_signal(self, raw: Optional[dict]) -> MacroSignalGroup:
        """从 macro_signal.json 转 MacroSignalGroup"""
        if raw is None:
            return MacroSignalGroup(conclusion=None, indicators=[])
        conclusion = raw.get("conclusion")
        data_date = raw.get("data_date")  # 'YYYY-MM-DD' 或 ISO timestamp
        # data_date 可能带时间(如 '2026-05-22T07:28:34Z'),取前 10 位
        date_only = data_date[:10] if isinstance(data_date, str) else None

        indicators = []
        details = raw.get("details") or {}
        for key, value in details.items():
            indicators.append(MacroIndicator(
                key=key,
                value=float(value) if isinstance(value, (int, float)) else None,
                updated_at=date_only,
            ))
        return MacroSignalGroup(conclusion=conclusion, indicators=indicators)

    def _convert_risk_appetite(self, raw: Optional[dict]) -> MacroSignalGroup:
        """从 risk_data.json 转 MacroSignalGroup(结构特殊,嵌套在 data.* 下)"""
        if raw is None:
            return MacroSignalGroup(conclusion=None, indicators=[])
        data = raw.get("data") or {}
        # score.conclusion 是定性结论
        conclusion = (raw.get("score") or {}).get("conclusion")
        # data.volume.date / data.turnover.date 是 'YYYY-MM-DD'
        vol_date = (data.get("volume") or {}).get("date")
        turn_date = (data.get("turnover") or {}).get("date")
        margin_date = (data.get("margin") or {}).get("date")

        indicators = []
        if data.get("volume"):
            indicators.append(MacroIndicator(
                key="total_amount_yi",
                value=(data["volume"].get("total_amount_yi")),
                updated_at=vol_date,
            ))
        if data.get("turnover"):
            indicators.append(MacroIndicator(
                key="turnover_rate",
                value=(data["turnover"].get("turnover_rate")),
                updated_at=turn_date,
            ))
        if data.get("margin"):
            indicators.append(MacroIndicator(
                key="margin_balance_yi",
                value=(data["margin"].get("rzye")),  # 融资余额,亿元
                updated_at=margin_date,
            ))
        return MacroSignalGroup(conclusion=conclusion, indicators=indicators)

    def get_snapshot(self, month: str) -> Optional[MacroSignalSnapshot]:
        """获取某月的 6 维度快照"""
        cache_key = f"snapshot:{month}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        groups = {}
        for dim_key, rel_path in DIMENSION_FILES.items():
            raw = self._read_json(rel_path)
            groups[dim_key] = self._convert_dimension_from_macro_signal(raw)
        # risk_appetite 单独处理
        risk_raw = self._read_json(RISK_APPETITE_FILE)
        groups["risk_appetite"] = self._convert_risk_appetite(risk_raw)

        # 数据日期检查:每个 skill 的 data_date 应该匹配请求的 month
        # 如果都不匹配,返回 None(代表该月无数据)
        any_match = any(
            (g.indicators and g.indicators[0].updated_at and g.indicators[0].updated_at.startswith(month))
            for g in groups.values()
        )
        if not any_match:
            logger.info(f"月份 {month} 无数据(macro-fin-skill 暂无快照)")
            return None

        # generated_at 用 risk_appetite(最频繁更新)的 date 或当前时间
        snapshot = MacroSignalSnapshot(
            month=month,
            groups=groups,
            generated_at=None,  # P0 不强制,前端不强依赖
        )
        self._set_cache(cache_key, snapshot)
        return snapshot

    def get_available_months(self) -> List[str]:
        """返回可用月份列表(降序)"""
        cache_key = "months"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        months = set()
        # 从 macro_signal.json 的 data_date 取 YYYY-MM
        for rel_path in DIMENSION_FILES.values():
            raw = self._read_json(rel_path)
            if raw is None:
                continue
            data_date = raw.get("data_date", "")
            if isinstance(data_date, str) and len(data_date) >= 7:
                months.add(data_date[:7])
        # 从 risk_data.json 取
        risk_raw = self._read_json(RISK_APPETITE_FILE)
        if risk_raw:
            data = risk_raw.get("data") or {}
            for sub in [data.get("volume"), data.get("turnover"), data.get("margin")]:
                if sub and sub.get("date"):
                    months.add(sub["date"][:7])

        sorted_months = sorted(months, reverse=True)
        self._set_cache(cache_key, sorted_months)
        return sorted_months


_singleton: Optional[MacroSignalService] = None


def get_macro_signal_service() -> MacroSignalService:
    global _singleton
    if _singleton is None:
        _singleton = MacroSignalService()
    return _singleton
```

## 6. 路由(`src/api/routes.py` 新增,放在文件末尾)

```python
# 在 routes.py 顶部 import 区域加:
from src.services.macro_signal_service import get_macro_signal_service
from src.models import (
    MacroSignalResponse, MacroSignalSnapshot, MacroMonthsResponse,
)

# 在文件末尾加 2 个路由:
@router.get("/macro/signal", response_model=MacroSignalResponse)
async def get_macro_signal(month: str = Query(..., description="月份 YYYY-MM")):
    """获取指定月份的宏观信号快照(6 维度)"""
    try:
        logger.info(f"查询宏观信号: month={month}")
        service = get_macro_signal_service()
        snapshot = service.get_snapshot(month)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"No data for month {month}")
        return MacroSignalResponse(success=True, data=snapshot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询宏观信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/months", response_model=MacroMonthsResponse)
async def get_macro_months():
    """获取当前可用的月份列表(降序)"""
    try:
        logger.info("查询可用月份列表")
        service = get_macro_signal_service()
        months = service.get_available_months()
        return MacroMonthsResponse(months=months)
    except Exception as e:
        logger.error(f"查询月份列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

## 7. 接口文档(`docs/MACRO_SIGNAL_API.md`)

完整列出 2 个接口的:
- 请求示例(curl)
- 响应 JSON 示例
- 字段表(类型 + 说明)
- 错误码(404 / 500)
- **agent 实施指南**:如何更新 macro-fin-skill 的 JSON 让前端拿到最新数据(关键:更新后无需重启后端,5 分钟缓存过期后自动加载)
- 数据源路径配置(`MACRO_SIGNAL_DATA_DIR` 环境变量)

## 8. 容错策略

| 场景 | 行为 |
|---|---|
| 单个 skill JSON 不存在 | 该维度返回 `{conclusion: null, indicators: []}`,其他维度正常 |
| 单个 skill JSON 损坏 | 同上 + log warning |
| 所有 6 个 JSON 都不匹配请求月份 | 返回 404 |
| 环境变量 `MACRO_SIGNAL_DATA_DIR` 路径不存在 | 启动时 service 第一次读时 log error,后续读全部走"维度缺失"分支 |

## 9. 验证方法

1. 本地起后端(`python -m uvicorn src.main:app --port 8094`)
2. curl 测试:
   - `curl http://localhost:8094/api/macro/signal?month=2026-05` → 期望 200 + 6 维度 JSON
   - `curl http://localhost:8094/api/macro/signal?month=2024-01` → 期望 404
   - `curl http://localhost:8094/api/macro/months` → 期望 `{"months":["2026-05"]}`
3. 跨进程:起前端 dev(`pnpm dev` 端口 3001),打开 http://localhost:3001/modules/economic,切到「宏观信号」Tab → 期望加载的是真实数据(不是 mock)