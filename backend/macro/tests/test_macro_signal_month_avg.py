"""month_avg 透传行为测试(日频指标月度口径)

固定今天 = 2026-08-17。断言口径见 prd.md 验收标准 1/2。
month_avg 与 value 同采样月,跟随按月过滤,不单独做月份匹配。
"""
from tests.conftest import make_macro_signal, write_skill_json


def _write_monetary_with_meta(skill_dir, details: dict, meta: dict):
    """写货币政策维度,indicator_meta 由调用方给定"""
    payload = make_macro_signal("2026-08-14", conclusion="偏宽松", details=details)
    payload["indicator_meta"] = meta
    write_skill_json(
        skill_dir, "monetary-policy-skill", "macro_signal.json", payload,
    )


def _write_risk_data(skill_dir, volume_block: dict):
    """写 risk_data.json,只填 volume 子块(其余子块留空)"""
    write_skill_json(
        skill_dir, "risk-appetite-skill", "risk_data.json",
        {
            "score": {"conclusion": "中性", "total_score": 55},
            "data": {"volume": volume_block},
        },
    )


class TestMonthAvgPassthrough:

    def test_macro_signal_month_avg_passthrough(self, skill_dir, service):
        """scenario: indicator_meta.dr007.month_avg → 快照 dr007.month_avg 透传"""
        _write_monetary_with_meta(
            skill_dir,
            details={"dr007": 1.70, "lpr_1y": 3.0},
            meta={
                "dr007": {"month_avg": 1.68},
                "lpr_1y": {},  # 月频无 month_avg
            },
        )

        snap = service.get_snapshot("2026-08")
        assert snap is not None
        by_key = {ind.key: ind for ind in snap.groups["monetary_policy"].indicators}

        assert by_key["dr007"].month_avg == 1.68
        assert by_key["dr007"].value == 1.70
        # 月频指标无 month_avg → None
        assert by_key["lpr_1y"].month_avg is None

    def test_month_avg_absent_is_null(self, skill_dir, service):
        """scenario: 旧格式 skill JSON(无 month_avg 字段)→ month_avg=None,解析不报错"""
        _write_monetary_with_meta(
            skill_dir,
            details={"dr007": 1.70},
            meta={"dr007": {"data_date": "2026-08-14"}},  # 无 month_avg
        )

        snap = service.get_snapshot("2026-08")
        assert snap is not None
        dr007 = {ind.key: ind for ind in snap.groups["monetary_policy"].indicators}["dr007"]
        assert dr007.month_avg is None
        assert dr007.value == 1.70

    def test_month_avg_not_numeric_ignored(self, skill_dir, service):
        """scenario: month_avg 是字符串(异常输出)→ None,不抛错"""
        _write_monetary_with_meta(
            skill_dir,
            details={"dr007": 1.70},
            meta={"dr007": {"month_avg": "1.68"}},
        )

        snap = service.get_snapshot("2026-08")
        assert snap is not None
        dr007 = {ind.key: ind for ind in snap.groups["monetary_policy"].indicators}["dr007"]
        assert dr007.month_avg is None

    def test_risk_data_month_avg_passthrough(self, skill_dir, service):
        """scenario: risk_data.json data.volume.month_avg → total_amount_yi.month_avg"""
        _write_risk_data(skill_dir, {
            "total_amount_yi": 18500,
            "date": "2026-08-14",
            "month_avg": 17800.5,
        })

        snap = service.get_snapshot("2026-08")
        assert snap is not None
        risk = snap.groups["risk_appetite"]
        total_amount = {ind.key: ind for ind in risk.indicators}["total_amount_yi"]
        assert total_amount.month_avg == 17800.5
        assert total_amount.value == 18500

    def test_placeholder_month_avg_stays_none(self, skill_dir, service):
        """scenario: 按月过滤转占位的指标(数据不在请求月)→ month_avg=None,不残留旧月均值"""
        _write_monetary_with_meta(
            skill_dir,
            details={"dr007": 1.65, "lpr_1y": 3.0},
            meta={"dr007": {"month_avg": 1.60}},  # 7 月推送,7 月月均
        )
        # 覆盖为 8 月数据但缺 dr007?不能——重写整个文件,dr007 变占位
        # 直接用 7 月数据请求 8 月(当前自然月):dr007 → 占位
        payload = make_macro_signal("2026-07-20", conclusion="偏宽松",
                                    details={"dr007": 1.65, "lpr_1y": 3.0})
        payload["indicator_meta"] = {"dr007": {"month_avg": 1.60, "data_date": "2026-07-20"}}
        write_skill_json(
            skill_dir, "monetary-policy-skill", "macro_signal.json", payload,
        )

        snap = service.get_snapshot("2026-08")
        assert snap is not None
        dr007 = {ind.key: ind for ind in snap.groups["monetary_policy"].indicators}["dr007"]
        # 占位态:value/month_avg 都为 None,只留预期发布日
        assert dr007.value is None
        assert dr007.month_avg is None
        assert dr007.next_release_at is not None
