"""宏观信号服务

读 macro-fin-skill 输出的 JSON,聚合成前端需要的 shape。

不重新实现 skill 计算逻辑,只做 IO + 格式转换。
"""
import json
import time
from datetime import date
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from src.config import get_settings
from src.models import MacroSignalSnapshot, MacroSignalGroup, MacroIndicator
from src.services.release_rules import get_next_release
from src.utils.logger import setup_logger

logger = setup_logger("macro_signal_service")


# 6 个 skill 的 dimension key → JSON 文件相对路径
DIMENSION_FILES = {
    "monetary_policy": "monetary-policy-skill/macro_signal.json",
    "money_supply":    "money-supply-skill/macro_signal.json",
    "entity_economy":  "entity-economy-skill/macro_signal.json",
    "inflation":       "inflation-skill/macro_signal.json",
    "exchange_rate":   "exchange-rate-skill/macro_signal.json",
}

# risk_appetite 是 risk_data.json(不是 macro_signal.json,结构也不同)
RISK_APPETITE_FILE = "risk-appetite-skill/risk_data.json"

# agent 推送写入白名单(防路径穿越；save_skill_json 只接受这些值)
ALLOWED_SKILLS = {
    "monetary-policy-skill", "money-supply-skill", "entity-economy-skill",
    "inflation-skill", "exchange-rate-skill", "risk-appetite-skill",
}
ALLOWED_FILES = {"macro_signal.json", "risk_data.json"}

# 6 个 dimension 的固定顺序(对齐前端 GROUP_ORDER)
DIMENSION_ORDER = [
    "monetary_policy", "money_supply", "entity_economy",
    "inflation", "exchange_rate", "risk_appetite",
]


class MacroSignalService:
    """单例服务(5 分钟内存缓存)"""

    def __init__(self):
        self.settings = get_settings()
        self._cache: Dict[str, tuple] = {}  # key → (timestamp, value)
        self._cache_ttl = 300  # 5 分钟

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ts, _ = self._cache[key]
        return (time.time() - ts) < self._cache_ttl

    def _get_cached(self, key: str):
        return self._cache[key][1] if self._is_cache_valid(key) else None

    def _set_cache(self, key: str, value: Any) -> None:
        self._cache[key] = (time.time(), value)

    def _read_json(self, rel_path: str) -> Optional[dict]:
        """读 skill JSON 文件,容错:缺失/损坏返回 None"""
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

    @staticmethod
    def _date10(value: Any) -> Optional[str]:
        """取 'YYYY-MM-DD' 前 10 位(兼容 ISO timestamp),非法返回 None"""
        return value[:10] if isinstance(value, str) and len(value) >= 10 else None

    def _resolve_next_release(self, key: str, data_date: Optional[str], self_reported: Any) -> Tuple[Optional[str], Optional[str]]:
        """下个周期预期:skill 自报优先,后端规则兜底。

        self_reported: { "date": 'YYYY-MM-DD', "note": str }(macro_signal 的
        indicator_meta[key].next_release 或 risk_data 的子块 next_release)。
        """
        if isinstance(self_reported, dict):
            reported_date = self._date10(self_reported.get("date"))
            if reported_date:
                note = self_reported.get("note")
                return reported_date, note if isinstance(note, str) else None

        # 规则兜底:基准日 = max(数据时间, 今天),保证「下次」一定在未来
        ref = date.today()
        if data_date:
            try:
                ref = max(date.fromisoformat(data_date), ref)
            except ValueError:
                pass  # data_date 格式异常,退化到今天
        computed = get_next_release(key, ref)
        return computed if computed else (None, None)

    def _convert_dimension_from_macro_signal(self, raw: Optional[dict]) -> MacroSignalGroup:
        """从 macro_signal.json 转 MacroSignalGroup

        三时间都是指标级,来源优先级:
        - data_date:   indicator_meta[key].data_date → 组级 data_date
        - analyzed_at: indicator_meta[key].analyzed_at → 组级 generated_at
        - next_release_at: indicator_meta[key].next_release(自报) → 后端规则兜底
        """
        if raw is None:
            return MacroSignalGroup(conclusion=None, total_score=None, indicators=[])

        conclusion = raw.get("conclusion")
        total_score = self._extract_total_score(raw)
        data_date = raw.get("data_date")  # 'YYYY-MM-DD' 或 ISO timestamp
        # data_date 可能带时间(如 '2026-05-22T07:28:34Z'),只取前 10 位
        date_only = data_date[:10] if isinstance(data_date, str) else None
        generated_at = raw.get("generated_at")  # skill 分析时间(ISO timestamp)

        meta = raw.get("indicator_meta")
        meta = meta if isinstance(meta, dict) else {}

        indicators: List[MacroIndicator] = []
        details = raw.get("details") or {}
        for key, value in details.items():
            if isinstance(value, (int, float)):
                m = meta.get(key)
                m = m if isinstance(m, dict) else {}
                ind_date = self._date10(m.get("data_date")) or date_only
                ind_analyzed = m.get("analyzed_at") or generated_at
                nr_at, nr_note = self._resolve_next_release(key, ind_date, m.get("next_release"))
                indicators.append(MacroIndicator(
                    key=key,
                    value=float(value),
                    updated_at=ind_date,  # 兼容别名 = data_date
                    data_date=ind_date,
                    analyzed_at=ind_analyzed if isinstance(ind_analyzed, str) else None,
                    next_release_at=nr_at,
                    next_release_note=nr_note,
                ))
            # 跳过非数值(value 是 None 或字符串),不写入 indicators

        return MacroSignalGroup(conclusion=conclusion, total_score=total_score, indicators=indicators)

    @staticmethod
    def _extract_total_score(raw: dict) -> Optional[float]:
        """提取维度总分:优先顶层 total_score,回退 score_detail.total_score"""
        for key in ("total_score",):
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        score_detail = raw.get("score_detail")
        if isinstance(score_detail, dict):
            value = score_detail.get("total_score")
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _convert_risk_appetite(self, raw: Optional[dict]) -> MacroSignalGroup:
        """从 risk_data.json 转 MacroSignalGroup(结构嵌套在 data.* 下)"""
        if raw is None:
            return MacroSignalGroup(conclusion=None, total_score=None, indicators=[])

        # score.conclusion 是定性结论(中文,例:「偏热/乐观」)
        score_block = raw.get("score") or {}
        conclusion = score_block.get("conclusion")

        data = raw.get("data") or {}

        # risk_data 的三时间天然指标级:子块 date=数据时间,子块 fetched_at=分析时间,
        # 子块 next_release=自报下期预期(缺失由后端规则兜底,三类都是每工作日)
        indicators: List[MacroIndicator] = []
        for sub_key, ind_key, field in (
            ("volume",   "两市成交额",   "total_amount_yi"),
            ("turnover", "换手率",       "turnover_rate"),
            ("margin",   "融资融券余额", "rzye"),  # rzye = 融资余额(亿元)
        ):
            block = data.get(sub_key) or {}
            if not block:
                continue
            ind_date = self._date10(block.get("date"))
            nr_at, nr_note = self._resolve_next_release(ind_key, ind_date, block.get("next_release"))
            indicators.append(MacroIndicator(
                key=ind_key,
                value=block.get(field),
                updated_at=ind_date,  # 兼容别名 = data_date
                data_date=ind_date,
                analyzed_at=block.get("fetched_at"),
                next_release_at=nr_at,
                next_release_note=nr_note,
            ))

        # score.total_score 是维度总分(0-100,skill 评分框架输出)
        total_score = score_block.get("total_score")
        if not isinstance(total_score, (int, float)):
            total_score = None

        return MacroSignalGroup(conclusion=conclusion, indicators=indicators, total_score=total_score)

    def get_snapshot(self, month: str) -> Optional[MacroSignalSnapshot]:
        """获取某月 6 维度快照;无数据返回 None"""
        cache_key = f"snapshot:{month}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # 读 6 个 skill JSON 并转 shape
        groups: Dict[str, MacroSignalGroup] = {}
        for dim_key, rel_path in DIMENSION_FILES.items():
            raw = self._read_json(rel_path)
            groups[dim_key] = self._convert_dimension_from_macro_signal(raw)
        # risk_appetite 单独处理
        risk_raw = self._read_json(RISK_APPETITE_FILE)
        groups["risk_appetite"] = self._convert_risk_appetite(risk_raw)

        # 数据日期检查:有任一维度的 indicator updated_at 落在请求月份内 → 视为该月有数据
        any_match = any(
            ind.updated_at is not None and ind.updated_at.startswith(month)
            for group in groups.values()
            for ind in group.indicators
        )
        if not any_match:
            logger.info(f"月份 {month} 无数据(macro-fin-skill 暂无快照)")
            return None

        # generated_at = 所有指标 analyzed_at 的最大值(同格式 ISO 字符串,字典序=时间序)
        analyzed_list = [
            ind.analyzed_at
            for group in groups.values()
            for ind in group.indicators
            if ind.analyzed_at
        ]

        snapshot = MacroSignalSnapshot(
            month=month,
            groups=groups,
            generated_at=max(analyzed_list) if analyzed_list else None,
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

        # 从 risk_data.json 取(月度切片用 volume.date / turnover.date / margin.date)
        risk_raw = self._read_json(RISK_APPETITE_FILE)
        if risk_raw:
            data = risk_raw.get("data") or {}
            for sub in [data.get("volume"), data.get("turnover"), data.get("margin")]:
                if sub and sub.get("date"):
                    months.add(sub["date"][:7])

        sorted_months = sorted(months, reverse=True)
        self._set_cache(cache_key, sorted_months)
        return sorted_months

    def save_skill_json(self, skill: str, file: str, data: dict) -> Path:
        """agent 推送写入:白名单校验 → 原子落盘 → 返回路径。违例抛 ValueError。"""
        if skill not in ALLOWED_SKILLS:
            raise ValueError(f"非法 skill: {skill}")
        if file not in ALLOWED_FILES:
            raise ValueError(f"非法 file: {file}")
        if not isinstance(data, dict):
            raise ValueError("data 必须是 JSON 对象")

        target_dir = Path(self.settings.macro_signal_data_dir) / skill
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / file
        # 原子写:临时文件 + replace,避免半写状态被读到
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(target_path)

        size = target_path.stat().st_size
        logger.info(f"skill JSON 已写入: {target_path} ({size} bytes)")
        return target_path

    def clear_cache(self) -> None:
        """清空内存缓存(写入后调用,让后续读立即生效,不必等 5 分钟 TTL)。"""
        self._cache.clear()
        logger.info("macro_signal 缓存已清空")


_singleton: Optional[MacroSignalService] = None


def get_macro_signal_service() -> MacroSignalService:
    global _singleton
    if _singleton is None:
        _singleton = MacroSignalService()
    return _singleton