"""全占位组的 conclusion/total_score 置空(卡头不显示旧月结论)

场景:8 月视图(数据全未发布)时,skill 5 月 JSON 的 conclusion「温和」
不应透出为 8 月的判断;整组无任何有值指标 → conclusion/total_score 置 null。
"""
from tests.conftest import make_macro_signal, write_skill_json


class TestGroupConclusionNull:
    def test_all_placeholder_group_nulls_conclusion(self, skill_dir, service):
        """全占位组:conclusion/total_score 置 null"""
        write_skill_json(
            skill_dir, "inflation-skill", "macro_signal.json",
            make_macro_signal("2026-07-09", conclusion="温和",
                              details={"cpi_yoy": 0.3}, ),
        )
        raw_extra = {"total_score": 66.0}
        import json as _json
        target = skill_dir / "inflation-skill" / "macro_signal.json"
        data = _json.loads(target.read_text(encoding="utf-8"))
        data.update(raw_extra)
        target.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")

        snap = service.get_snapshot("2026-08")
        g = snap.groups["inflation"]
        assert g.conclusion is None
        assert g.total_score is None
        assert all(i.value is None for i in g.indicators)

    def test_partial_placeholder_group_keeps_conclusion(self, skill_dir, service):
        """部分占位组(月频未出但日频已有值):conclusion 维持透出"""
        write_skill_json(
            skill_dir, "monetary-policy-skill", "macro_signal.json",
            make_macro_signal("2026-08-14", conclusion="偏宽松",
                              details={"dr007": 1.70, "lpr_1y": 3.0}),
        )
        snap = service.get_snapshot("2026-08")
        g = snap.groups["monetary_policy"]
        assert g.conclusion == "偏宽松"
        by_key = {i.key: i for i in g.indicators}
        assert by_key["dr007"].value == 1.70

    def test_archive_group_keeps_conclusion(self, skill_dir, service):
        """归档组:conclusion 全量透出不受影响(归档即真源)"""
        import json as _json
        write_skill_json(
            skill_dir, "inflation-skill", "macro_signal.json",
            make_macro_signal("2026-07-09", conclusion="温和", details={"cpi_yoy": 0.3}),
        )
        arch = skill_dir / "archive" / "2026-07"
        arch.mkdir(parents=True)
        (arch / "inflation-skill.json").write_text(
            _json.dumps(make_macro_signal("2026-07-09", conclusion="温和",
                                          details={"cpi_yoy": 0.3}),
                        ensure_ascii=False), encoding="utf-8")

        snap = service.get_snapshot("2026-07")
        g = snap.groups["inflation"]
        assert g.conclusion == "温和"
        assert {i.key: i for i in g.indicators}["cpi_yoy"].value == 0.3
