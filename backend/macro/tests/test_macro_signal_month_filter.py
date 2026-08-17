"""按月过滤 + 暂未获取占位(兜底路径)的行为测试

固定今天 = 2026-08-17,平铺数据 = 7 月(月频)/ 未发布 8 月。
断言口径见 prd.md 验收标准 1/2/3/5。
"""
import json

from tests.conftest import make_macro_signal, write_skill_json

# 六维度各自一个代表指标(都在 INDICATOR_RELEASE_RULES 里)
INFLATION_JUL = {
    "cpi_yoy": 0.3,
    "ppi_yoy": -1.2,
}
MONETARY_JUL = {
    "dr007": 1.65,   # 日频
    "lpr_1y": 3.0,   # 月频,每月20日
}


def _write_july_flat(skill_dir):
    """平铺写入 7 月数据的通胀 + 货币政策两个维度"""
    write_skill_json(
        skill_dir, "inflation-skill", "macro_signal.json",
        make_macro_signal("2026-07-09", conclusion="温和", details=INFLATION_JUL),
    )
    write_skill_json(
        skill_dir, "monetary-policy-skill", "macro_signal.json",
        make_macro_signal("2026-07-20", conclusion="偏宽松", details=MONETARY_JUL),
    )


class TestFallbackMonthFilter:
    """兜底路径(archive 不存在)的按月过滤"""

    def test_request_latest_month_filters_out_other_month(self, skill_dir, service):
        """场景:8 月请求,月频 CPI(7 月数据)→ 占位 value=null + 预期发布日"""
        _write_july_flat(skill_dir)

        # 注意:该 fixture 目录里 8 月没有任何指标数据,先造一个 8 月日频指标
        # 让 latest_month = 2026-08(模拟 DR007 已更新到 8 月)
        write_skill_json(
            skill_dir, "monetary-policy-skill", "macro_signal.json",
            make_macro_signal("2026-08-14", conclusion="偏宽松",
                              details={"dr007": 1.70, "lpr_1y": 3.0}),
        )

        snap = service.get_snapshot("2026-08")
        assert snap is not None

        monetary = snap.groups["monetary_policy"]
        by_key = {ind.key: ind for ind in monetary.indicators}

        # dr007 落在 8 月 → 保留数值
        assert by_key["dr007"].value == 1.70
        assert by_key["dr007"].data_date == "2026-08-14"

        # lpr_1y 数据时间是 7 月组级 data_date(2026-08-14)——本例里月频
        # 已在 8 月,不占位;真正的月频占位断言在通胀组(数据还是 7 月)
        inflation = snap.groups["inflation"]
        inf_by_key = {ind.key: ind for ind in inflation.indicators}
        assert inf_by_key["cpi_yoy"].value is None
        assert inf_by_key["cpi_yoy"].data_date is None
        # CPI 每月 9 日发布,7 月数据已发布,8 月数据 → 2026-09-09
        assert inf_by_key["cpi_yoy"].next_release_at == "2026-09-09"
        assert inf_by_key["ppi_yoy"].value is None

    def test_request_current_natural_month_all_placeholder(self, skill_dir, service):
        """场景:8 月(当前自然月)无任何数据落月 → 全占位,不返回 None"""
        _write_july_flat(skill_dir)  # 只有 7 月数据

        snap = service.get_snapshot("2026-08")
        assert snap is not None, "当前自然月即使无数据也应返回全占位快照"

        inflation = snap.groups["inflation"]
        assert len(inflation.indicators) > 0
        for ind in inflation.indicators:
            assert ind.value is None
            assert ind.data_date is None
            assert ind.next_release_at is not None

    def test_historical_hole_month_returns_none(self, skill_dir, service):
        """场景:早于 latest_month 且无归档的历史空洞月 → None"""
        write_skill_json(
            skill_dir, "inflation-skill", "macro_signal.json",
            make_macro_signal("2026-07-09", details=INFLATION_JUL),
        )
        assert service.get_snapshot("2026-06") is None

    def test_archive_month_full_return(self, skill_dir, service):
        """场景:归档月全量返回,不受过滤影响"""
        _write_july_flat(skill_dir)
        # 归档 7 月(内容与平铺一致即可,语义=归档即真源)
        archive = skill_dir / "archive" / "2026-07"
        archive.mkdir(parents=True)
        (archive / "inflation-skill.json").write_text(
            json.dumps(make_macro_signal("2026-07-09", details=INFLATION_JUL),
                       ensure_ascii=False), encoding="utf-8")

        snap = service.get_snapshot("2026-07")
        assert snap is not None
        cpi = {i.key: i for i in snap.groups["inflation"].indicators}["cpi_yoy"]
        assert cpi.value == 0.3
        assert cpi.data_date == "2026-07-09"

    def test_unknown_rule_key_dropped(self, skill_dir, service):
        """场景:规则表查不到的 key,数据不在请求月 → 剔除,不占位"""
        write_skill_json(
            skill_dir, "inflation-skill", "macro_signal.json",
            make_macro_signal("2026-07-09",
                              details={"cpi_yoy": 0.3, "神秘新指标": 1.0}),
        )
        snap = service.get_snapshot("2026-08")
        keys = {i.key for i in snap.groups["inflation"].indicators}
        # 神秘新指标:数据不在 8 月,且无规则可推预期 → 剔除
        assert "神秘新指标" not in keys
        # cpi_yoy:数据不在 8 月,但有规则 → 占位保留
        assert "cpi_yoy" in keys
        cpi = {i.key: i for i in snap.groups["inflation"].indicators}["cpi_yoy"]
        assert cpi.value is None
