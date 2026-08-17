"""宏观信号服务

读 macro-fin-skill 输出的 JSON,聚合成前端需要的 shape。

不重新实现 skill 计算逻辑,只做 IO + 格式转换。
"""
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple

from src.config import get_settings
from src.models import MacroSignalSnapshot, MacroSignalGroup, MacroIndicator
from src.services.release_rules import get_next_release, get_frequency, INDICATOR_RELEASE_RULES
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

# 归档月份格式 'YYYY-MM'(month 会拼入归档路径,严格校验防穿越)
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")

# dimension key → skill 目录名(归档文件名 = <skill 目录名>.json)
DIMENSION_SKILL_DIRS = {
    "monetary_policy": "monetary-policy-skill",
    "money_supply":    "money-supply-skill",
    "entity_economy":  "entity-economy-skill",
    "inflation":       "inflation-skill",
    "exchange_rate":   "exchange-rate-skill",
    "risk_appetite":   "risk-appetite-skill",
}


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

    def _read_json(self, rel_path: str) -> Tuple[Optional[dict], Optional[str]]:
        """读 skill JSON 文件,容错:缺失/损坏返回 (None, None)。

        同时返回文件 mtime(UTC ISO)——skill 未自报 analyzed_at/generated_at 时,
        它就是「分析/推送时间」的最后兜底(agent 推送写入 = mtime 即推送时间)。
        """
        full_path = Path(self.settings.macro_signal_data_dir) / rel_path
        try:
            with open(full_path, encoding="utf-8") as f:
                raw = json.load(f)
            mtime = datetime.fromtimestamp(full_path.stat().st_mtime, tz=timezone.utc)
            return raw, mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
        except FileNotFoundError:
            logger.warning(f"macro-signal JSON 不存在: {full_path}")
            return None, None
        except json.JSONDecodeError as e:
            logger.warning(f"macro-signal JSON 解析失败: {full_path} - {e}")
            return None, None

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

    def _placeholder_indicator(self, key: str) -> Optional[MacroIndicator]:
        """构造「暂未获取」占位指标:value/data_date 为空,发布预期走规则表。

        规则表查不到的 key 返回 None(调用方剔除——无规则可推预期,不造占位)。
        next_release 基准日 = 今天(_resolve_next_release 数据时间为 None 时
        自然落到今天,推算出「请求月数据」的发布日)。
        """
        nr_at, nr_note = self._resolve_next_release(key, None, None)
        freq = get_frequency(key)
        if nr_at is None or freq is None:
            return None
        return MacroIndicator(
            key=key,
            value=None,
            updated_at=None,
            data_date=None,
            analyzed_at=None,
            next_release_at=nr_at,
            next_release_note=nr_note,
            frequency=freq,
        )

    def _convert_dimension_from_macro_signal(
        self, raw: Optional[dict], file_mtime: Optional[str] = None,
        month: Optional[str] = None,
    ) -> MacroSignalGroup:
        """从 macro_signal.json 转 MacroSignalGroup

        三时间都是指标级,来源优先级(自报优先、规则兜底):
        - data_date:   indicator_meta[key].data_date → 组级 data_date
        - analyzed_at: indicator_meta[key].analyzed_at → 组级 generated_at → 文件 mtime(推送时间)
        - next_release_at: indicator_meta[key].next_release(自报) → 后端规则兜底
        - frequency:   indicator_meta[key].frequency(自报,'daily'/'monthly') → 规则表 kind 推导

        month(兜底路径按月过滤):指标 data_date 落在请求月才保留原值,
        否则转占位(value=null + 规则推算 next_release)。None = 不过滤(归档路径)。
        """
        if raw is None:
            return MacroSignalGroup(conclusion=None, total_score=None, indicators=[])

        conclusion = raw.get("conclusion")
        total_score = self._extract_total_score(raw)
        data_date = raw.get("data_date")  # 'YYYY-MM-DD' 或 ISO timestamp
        # data_date 可能带时间(如 '2026-05-22T07:28:34Z'),只取前 10 位
        date_only = data_date[:10] if isinstance(data_date, str) else None
        generated_at = raw.get("generated_at") or file_mtime  # skill 分析时间,缺失用文件 mtime 兜底

        meta = raw.get("indicator_meta")
        meta = meta if isinstance(meta, dict) else {}

        indicators: List[MacroIndicator] = []
        details = raw.get("details") or {}
        for key, value in details.items():
            if isinstance(value, (int, float)):
                m = meta.get(key)
                m = m if isinstance(m, dict) else {}
                ind_date = self._date10(m.get("data_date")) or date_only
                # 按月过滤:data_date 不在请求月 → 占位(非请求月数据不冒充请求月)
                if month is not None and not (ind_date or "").startswith(month):
                    ph = self._placeholder_indicator(key)
                    if ph is not None:
                        indicators.append(ph)
                    continue
                ind_analyzed = m.get("analyzed_at") or generated_at
                nr_at, nr_note = self._resolve_next_release(key, ind_date, m.get("next_release"))
                freq = m.get("frequency")
                freq = freq if freq in ("daily", "monthly") else get_frequency(key)
                indicators.append(MacroIndicator(
                    key=key,
                    value=float(value),
                    updated_at=ind_date,  # 兼容别名 = data_date
                    data_date=ind_date,
                    analyzed_at=ind_analyzed if isinstance(ind_analyzed, str) else None,
                    next_release_at=nr_at,
                    next_release_note=nr_note,
                    frequency=freq,
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

    def _convert_risk_appetite(
        self, raw: Optional[dict], file_mtime: Optional[str] = None,
        month: Optional[str] = None,
    ) -> MacroSignalGroup:
        """从 risk_data.json 转 MacroSignalGroup(结构嵌套在 data.* 下)

        month 语义同 _convert_dimension_from_macro_signal(兜底路径按月过滤)。
        """
        if raw is None:
            return MacroSignalGroup(conclusion=None, total_score=None, indicators=[])

        # score.conclusion 是定性结论(中文,例:「偏热/乐观」)
        score_block = raw.get("score") or {}
        conclusion = score_block.get("conclusion")

        data = raw.get("data") or {}
        data_fetched_at = data.get("fetched_at") or file_mtime  # 顶层拉取时间,缺失用 mtime 兜底

        # risk_data 的三时间天然指标级:子块 date=数据时间,子块 fetched_at=分析时间,
        # 子块 next_release/frequency=自报下期预期与频率(缺失由后端规则兜底,三者都是每工作日)
        indicators: List[MacroIndicator] = []
        for sub_key, ind_key, field in (
            ("volume",   "total_amount_yi",   "total_amount_yi"),  # 两市成交额
            ("turnover", "turnover_rate",     "turnover_rate"),    # 换手率
            ("margin",   "margin_balance_yi", "rzye"),             # 融资融券余额(rzye=融资余额,亿元)
        ):
            block = data.get(sub_key) or {}
            if not block:
                continue
            ind_date = self._date10(block.get("date"))
            # 按月过滤:data_date 不在请求月 → 占位
            if month is not None and not (ind_date or "").startswith(month):
                ph = self._placeholder_indicator(ind_key)
                if ph is not None:
                    indicators.append(ph)
                continue
            nr_at, nr_note = self._resolve_next_release(ind_key, ind_date, block.get("next_release"))
            freq = block.get("frequency")
            freq = freq if freq in ("daily", "monthly") else get_frequency(ind_key)
            indicators.append(MacroIndicator(
                key=ind_key,
                value=block.get(field),
                updated_at=ind_date,  # 兼容别名 = data_date
                data_date=ind_date,
                analyzed_at=block.get("fetched_at") or data_fetched_at,
                next_release_at=nr_at,
                next_release_note=nr_note,
                frequency=freq,
            ))

        # score.total_score 是维度总分(0-100,skill 评分框架输出)
        total_score = score_block.get("total_score")
        if not isinstance(total_score, (int, float)):
            total_score = None

        return MacroSignalGroup(conclusion=conclusion, indicators=indicators, total_score=total_score)

    def _read_archive_groups(self, month: str) -> Optional[Dict[str, MacroSignalGroup]]:
        """读 archive/<month>/ 下 6 个归档文件并转 shape;目录不存在返回 None。

        目录存在但某 skill 归档缺失 → 该维度空 group(与平铺「维度缺失」语义一致)。
        """
        archive_dir = Path(self.settings.macro_signal_data_dir) / "archive" / month
        if not archive_dir.is_dir():
            return None

        groups: Dict[str, MacroSignalGroup] = {}
        for dim_key, skill_dir in DIMENSION_SKILL_DIRS.items():
            raw, file_mtime = self._read_json(f"archive/{month}/{skill_dir}.json")
            if dim_key == "risk_appetite":
                groups[dim_key] = self._convert_risk_appetite(raw, file_mtime)
            else:
                groups[dim_key] = self._convert_dimension_from_macro_signal(raw, file_mtime)
        return groups

    def _read_latest_groups(self, month: Optional[str] = None) -> Dict[str, MacroSignalGroup]:
        """读平铺最新 6 个 skill JSON 并转 shape(mtime 作为 analyzed_at 的最后兜底)

        month 非 None 时按月过滤+占位(兜底路径语义)。
        """
        groups: Dict[str, MacroSignalGroup] = {}
        for dim_key, rel_path in DIMENSION_FILES.items():
            raw, file_mtime = self._read_json(rel_path)
            groups[dim_key] = self._convert_dimension_from_macro_signal(raw, file_mtime, month)
        # risk_appetite 单独处理
        risk_raw, risk_mtime = self._read_json(RISK_APPETITE_FILE)
        groups["risk_appetite"] = self._convert_risk_appetite(risk_raw, risk_mtime, month)
        return groups

    def get_snapshot(self, month: str) -> Optional[MacroSignalSnapshot]:
        """获取某月 6 维度快照;无数据返回 None。

        读取优先级:archive/<month>/(按月归档,生产真源) → 平铺最新文件
        (本地开发直读 skill 仓库 / 归档未覆盖的存量月兜底,按月过滤:
        非请求月的指标转「暂未获取」占位,不冒充请求月数据)。
        请求月早于最新数据月且无归档 → None(历史空洞月)。
        """
        # month 会拼入归档路径,严格格式校验防穿越
        if not isinstance(month, str) or not MONTH_PATTERN.match(month):
            return None

        cache_key = f"snapshot:{month}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        # 归档优先:archive/<month>/ 存在 → 直接用归档(部分 skill 缺失 → 空维度)
        groups = self._read_archive_groups(month)
        if groups is None:
            # 兜底:读平铺最新 6 文件,按月过滤(非请求月指标 → 占位)
            groups = self._read_latest_groups(month)
            any_match = any(
                ind.data_date is not None and ind.data_date.startswith(month)
                for group in groups.values()
                for ind in group.indicators
            )
            if not any_match:
                # 无任何指标落在请求月:当前/未来月返回全占位(暂未获取+预期发布),
                # 历史月数据不会再补 → None
                if month < date.today().strftime("%Y-%m"):
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

        # 归档月:archive/ 子目录名(仅保留 YYYY-MM 合法者,生产真源)
        archive_dir = Path(self.settings.macro_signal_data_dir) / "archive"
        if archive_dir.is_dir():
            for sub in archive_dir.iterdir():
                if sub.is_dir() and MONTH_PATTERN.match(sub.name):
                    months.add(sub.name)

        # 平铺最新文件的月份(存量未归档月兜底):从 macro_signal.json 的 data_date 取 YYYY-MM
        for rel_path in DIMENSION_FILES.values():
            raw, _ = self._read_json(rel_path)
            if raw is None:
                continue
            data_date = raw.get("data_date", "")
            if isinstance(data_date, str) and len(data_date) >= 7:
                months.add(data_date[:7])

        # 从 risk_data.json 取(月度切片用 volume.date / turnover.date / margin.date)
        risk_raw, _ = self._read_json(RISK_APPETITE_FILE)
        if risk_raw:
            data = risk_raw.get("data") or {}
            for sub in [data.get("volume"), data.get("turnover"), data.get("margin")]:
                if sub and sub.get("date"):
                    months.add(sub["date"][:7])

        sorted_months = sorted(months, reverse=True)
        self._set_cache(cache_key, sorted_months)
        return sorted_months

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """原子写 JSON:临时文件 + replace,避免半写状态被读到"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(path)

    @staticmethod
    def _extract_archive_month(file: str, data: Optional[dict]) -> Optional[str]:
        """从 skill JSON 提取归档月份 'YYYY-MM';提取不到返回 None(格式非法视为提取不到)

        - macro_signal.json: 顶层 data_date 前 7 位
        - risk_data.json:    data.{volume,turnover,margin}.date 最大值的前 7 位
        """
        if not isinstance(data, dict):
            return None

        def _norm(value: Any) -> Optional[str]:
            month = value[:7] if isinstance(value, str) and len(value) >= 7 else None
            return month if month and MONTH_PATTERN.match(month) else None

        if file == "risk_data.json":
            data_block = data.get("data") or {}
            sub_dates = [
                sub.get("date") for sub in (
                    data_block.get("volume"), data_block.get("turnover"), data_block.get("margin"),
                ) if isinstance(sub, dict)
            ]
            valid = [m for m in (_norm(d) for d in sub_dates) if m]
            return max(valid) if valid else None
        return _norm(data.get("data_date"))

    def _archive_skill_json(self, skill: str, month: str, data: dict) -> Path:
        """归档 skill JSON 到 archive/<month>/<skill>.json(原子写)"""
        archive_path = (
            Path(self.settings.macro_signal_data_dir) / "archive" / month / f"{skill}.json"
        )
        self._atomic_write_json(archive_path, data)
        logger.info(f"skill JSON 已归档: {archive_path} ({archive_path.stat().st_size} bytes)")
        return archive_path

    def save_skill_json(self, skill: str, file: str, data: dict) -> Tuple[Path, Optional[str]]:
        """agent 推送写入(按月留存):白名单校验 → 抢救归档旧文件 → 覆盖最新文件 → 归档当月。

        返回 (最新文件路径, 归档月份);违例抛 ValueError。
        抢救归档保证历史月零丢失:跨月推送自动留存上月,部署后首推自动迁移存量;
        同月重推时第 1 步产物会被第 3 步覆盖,幂等。
        """
        if skill not in ALLOWED_SKILLS:
            raise ValueError(f"非法 skill: {skill}")
        if file not in ALLOWED_FILES:
            raise ValueError(f"非法 file: {file}")
        if not isinstance(data, dict):
            raise ValueError("data 必须是 JSON 对象")

        latest_path = Path(self.settings.macro_signal_data_dir) / skill / file

        # 1. 抢救归档:旧最新文件在被覆盖前按其数据月份留存(提取不到月份则跳过)
        old_raw, _ = self._read_json(f"{skill}/{file}")
        if old_raw is not None:
            old_month = self._extract_archive_month(file, old_raw)
            if old_month:
                self._archive_skill_json(skill, old_month, old_raw)
            else:
                logger.warning(f"旧 skill JSON 提取不到归档月份,跳过抢救归档: {latest_path}")

        # 2. 覆盖写最新文件(原子写)
        self._atomic_write_json(latest_path, data)
        logger.info(f"skill JSON 已写入: {latest_path} ({latest_path.stat().st_size} bytes)")

        # 3. 归档当月(提取失败不阻塞写入,仅跳过归档)
        new_month = self._extract_archive_month(file, data)
        if new_month:
            self._archive_skill_json(skill, new_month, data)
        else:
            logger.warning(f"推送 data 提取不到归档月份,跳过归档: skill={skill} file={file}")

        return latest_path, new_month

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