"""valuation_service 编排测试（假 Hermes：注入 submit/poll 双函数，不真连）。"""
import asyncio
import json

import pytest

from src.api.models import DividendStock
from src.services.hermes_client import HermesApiError, HermesConfig, HermesRunFailed
from src.services.valuation_service import (
    ValuationService,
    build_prompt,
    build_valuation_payload,
    parse_valuation_output,
)
from src.services.refresh_jobs import RefreshJobManager

CFG = HermesConfig(base_url="http://nas:8642", api_key="secret", profile="ohyes768",
                   poll_interval=0, timeout=5, max_concurrent=4)


def stock(**updates):
    fields = dict(code="000001", name="样本", exchange="深市主板", avg_yield_3y=4.2,
                  roe=12.5, roe_avg_3y=13, roe_year=2025,
                  roe_history=[dict(year=y, value=13) for y in [2023, 2024, 2025]])
    fields.update(updates)
    return DividendStock(**fields)


def fake_report(code, name, status="ready", *, skill_version="1.0.0", code_mismatch=False):
    body = {
        "schema_version": "1.0.0",
        "skill_version": skill_version,
        "code": "999999" if code_mismatch else code,
        "name": name,
        "currency": "CNY",
        "as_of": "2026-11-11",
        "status": status,
        "levels": None,
        "valuation": None,
        "evidence": [{"id": "e1", "title": "年报摘要", "kind": "official", "origin": "inline:2026-11-11:年报",
                      "locator": "第二节", "period": "2025 年度", "published_at": "2026-03-30",
                      "accessed_at": "2026-11-11", "verification": "reused"}],
        "data_gaps": [],
        "confidence": {"level": "medium", "reason": "证据来自上游复用"},
        "risks": ["分红波动"],
        "invalidation_conditions": ["分红政策变更"],
        "summary": "四点均有依据" if status == "ready" else "核心材料不足",
        "analysis": {
            "business": "生意稳定", "normalization": "盈利正常化", "dividend": "分红可持续",
            "valuation": "PE 为主", "risk": "风险可控",
        },
        "report_md": "# 四挡位估值\n\n## 摘要\n内容完整",
    }
    if status == "ready":
        body["levels"] = {
            "heavy_position": {"price": 10.0, "pe": 5.1, "pb": 0.7},
            "add_position": {"price": 12.0, "pe": 6.1, "pb": 0.8},
            "reduce_position": {"price": 15.0, "pe": 7.6, "pb": 1.0},
            "full_exit": {"price": 19.0, "pe": 9.7, "pb": 1.3},
        }
        body["valuation"] = {
            "primary_method": "pe_multiple",
            "anchor": "正常化 EPS 1.5 元",
            "scenarios": {"bear": {"model": "pe_multiple", "rationale": "悲观", "evidence_ids": ["e1"]}},
            "decisions": {"heavy_position": {"model": "pe_multiple", "rationale": "重仓", "evidence_ids": ["e1"]}},
            "metric_inputs": {"ttm_eps": 1.5, "common_bvps": None, "annual_dps": 0.5,
                              "dps_basis": "forward_ordinary", "period": "2025", "share_basis": "总股本",
                              "evidence_ids": ["e1"]},
            "sensitivity": [{"label": "EPS -20%", "base_level": "heavy_position", "model": "pe_multiple",
                             "rationale": "盈利下修", "evidence_ids": ["e1"]}],
        }
    return json.dumps(body, ensure_ascii=False)


def run_service(tmp_path, codes, stocks, submit_fn, poll_fn, *, quality_scores=None, snapshot_fn=None,
                data_date="2026-09-30"):
    async def scenario():
        service = ValuationService(tmp_path / "valuation_reports.json")
        manager = RefreshJobManager(tmp_path / "jobs")
        job = service.submit_valuation(codes, CFG, stocks, data_date, manager,
                                       quality_scores or {}, submit_fn, poll_fn,
                                       market_snapshot_fn=snapshot_fn)
        await manager.close(timeout=5)
        return service, manager.get(job["job_id"])
    return asyncio.run(scenario())


class TestParse:
    def test_ready_report_parses(self):
        report = parse_valuation_output(fake_report("000001", "样本"), "000001", "样本")
        assert report.status == "ready"
        assert report.levels["heavy_position"].price == 10.0
        assert report.levels["full_exit"].price == 19.0
        assert report.valuation["primary_method"] == "pe_multiple"

    def test_fenced_json_parses(self):
        raw = "```json\n" + fake_report("000001", "样本") + "\n```"
        assert parse_valuation_output(raw, "000001", "样本").code == "000001"

    def test_prefixed_json_parses(self):
        raw = "评估结果如下：\n" + fake_report("000001", "样本") + "\n以上。"
        assert parse_valuation_output(raw, "000001", "样本").status == "ready"

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_valuation_output("抱歉，我无法完成该任务。", "000001", "样本")

    def test_code_mismatch_rejected(self):
        raw = fake_report("000001", "样本", code_mismatch=True)
        with pytest.raises(ValueError, match="不一致"):
            parse_valuation_output(raw, "000001", "样本")

    def test_insufficient_data_parses_and_normalizes(self):
        raw = fake_report("000001", "样本", status="insufficient_data")
        report = parse_valuation_output(raw, "000001", "样本")
        assert report.status == "insufficient_data"
        assert report.levels is None
        assert report.valuation is None
        assert report.analysis["business"] == "生意稳定"

    def test_non_ready_with_levels_rejected(self):
        raw = fake_report("000001", "样本", status="insufficient_data")
        data = json.loads(raw)
        data["levels"] = {"heavy_position": {"price": 10.0, "pe": None, "pb": None}}
        with pytest.raises(ValueError, match="四点全 null"):
            parse_valuation_output(json.dumps(data, ensure_ascii=False), "000001", "样本")

    def test_non_ready_with_valuation_rejected(self):
        raw = fake_report("000001", "样本", status="blocked")
        data = json.loads(raw)
        data["valuation"] = {"primary_method": "pe_multiple"}
        with pytest.raises(ValueError, match="必须为 null"):
            parse_valuation_output(json.dumps(data, ensure_ascii=False), "000001", "样本")

    def test_ready_levels_not_increasing_rejected(self):
        raw = fake_report("000001", "样本")
        data = json.loads(raw)
        data["levels"]["add_position"]["price"] = 9.0
        with pytest.raises(ValueError, match="严格递增"):
            parse_valuation_output(json.dumps(data, ensure_ascii=False), "000001", "样本")

    def test_ready_missing_level_rejected(self):
        raw = fake_report("000001", "样本")
        data = json.loads(raw)
        del data["levels"]["full_exit"]
        with pytest.raises(ValueError, match="四键"):
            parse_valuation_output(json.dumps(data, ensure_ascii=False), "000001", "样本")

    def test_bad_currency_rejected(self):
        raw = fake_report("000001", "样本").replace('"currency": "CNY"', '"currency": "USD"')
        with pytest.raises(ValueError, match="CNY"):
            parse_valuation_output(raw, "000001", "样本")

    def test_bad_confidence_rejected(self):
        raw = fake_report("000001", "样本").replace('"level": "medium"', '"level": "sure"')
        with pytest.raises(ValueError):
            parse_valuation_output(raw, "000001", "样本")

    def test_bad_skill_version_rejected(self):
        raw = fake_report("000001", "样本", skill_version="dev")
        with pytest.raises(ValueError):
            parse_valuation_output(raw, "000001", "样本")

    def test_duplicate_evidence_id_rejected(self):
        raw = fake_report("000001", "样本")
        data = json.loads(raw)
        data["evidence"].append(dict(data["evidence"][0]))
        with pytest.raises(ValueError, match="id 重复"):
            parse_valuation_output(json.dumps(data, ensure_ascii=False), "000001", "样本")

    def test_analysis_section_missing_rejected(self):
        raw = fake_report("000001", "样本")
        data = json.loads(raw)
        del data["analysis"]["risk"]
        with pytest.raises(ValueError, match="五段"):
            parse_valuation_output(json.dumps(data, ensure_ascii=False), "000001", "样本")


class TestPayloadAndPrompt:
    def test_payload_includes_rating_and_market(self):
        payload = build_valuation_payload(
            stock(), {"skill_version": "4.4.0", "dimensions": {"business": 4}, "summary": "s"},
            {"realtime": 12.5, "close": 12.4, "pe": 8.0, "pb": 1.1})
        assert payload["market_snapshot"]["realtime"] == 12.5
        assert "不得按现价比例" in payload["market_snapshot"]["note"]
        assert payload["existing_quality_rating"]["skill_version"] == "4.4.0"
        assert payload["eps_year"] is None or isinstance(payload["eps_year"], int)

    def test_payload_without_rating_has_no_key(self):
        payload = build_valuation_payload(stock(), None, None)
        assert "existing_quality_rating" not in payload
        assert payload["market_snapshot"]["realtime"] is None

    def test_prompt_names_skill_and_demands_bare_json(self):
        prompt = build_prompt(build_valuation_payload(stock(), None, None), "1.0.0", "2026-09-30")
        assert "stock-four-level-valuation" in prompt
        assert "JSON" in prompt
        assert "1.0.0" in prompt
        assert "2026-09-30" in prompt


class TestSubmitValuation:
    def test_duration_and_persistence(self, tmp_path, monkeypatch):
        from src.services import valuation_service

        clock = [100.0]
        monkeypatch.setattr(valuation_service, "monotonic", lambda: clock[0], raising=False)

        def submit_fn(cfg, prompt, key):
            clock[0] += 2.0
            return "run-1"

        def poll_fn(cfg, run_id):
            clock[0] += 30.5
            return fake_report("000001", "样本")

        service, job = run_service(tmp_path, ["000001"], {"000001": stock()}, submit_fn, poll_fn)
        assert job["status"] == "succeeded"
        saved = ValuationService(service.reports_path).get_all()["000001"]
        assert saved["analysis_duration_seconds"] == 32.5
        assert saved["status"] == "ready"
        assert saved["data_date"] == "2026-09-30"
        assert saved["evaluated_at"]

    def test_two_stocks_and_non_ready_saved(self, tmp_path):
        runs = {}

        def submit_fn(cfg, prompt, key):
            code = key.split("-")[1]
            runs[key] = code
            return key  # run_id 用幂等键本身，便于 poll 侧识别

        def poll_fn(cfg, run_id):
            code = runs[run_id]
            if code == "000001":
                return fake_report("000001", "样本")
            return fake_report("600000", "浦发", status="insufficient_data")

        service, job = run_service(tmp_path, ["000001", "600000"],
                                   {"000001": stock(), "600000": stock(code="600000", name="浦发")},
                                   submit_fn, poll_fn)
        assert job["status"] == "succeeded"
        saved = ValuationService(service.reports_path).get_all()
        assert saved["000001"]["status"] == "ready"
        assert saved["600000"]["status"] == "insufficient_data"
        assert saved["600000"]["levels"] is None

    def test_failed_poll_marks_failed(self, tmp_path):
        def submit_fn(cfg, prompt, key):
            return "run-1"

        def poll_fn(cfg, run_id):
            raise HermesRunFailed("run run-1 终态 failed")

        service, job = run_service(tmp_path, ["000001"], {"000001": stock()}, submit_fn, poll_fn)
        assert job["status"] == "failed"
        assert "000001" in job["failed_codes"]
        assert ValuationService(service.reports_path).get_all() == {}

    def test_version_mismatch_rejected_and_old_report_kept(self, tmp_path, monkeypatch):
        from src.services import valuation_service as vs
        monkeypatch.setenv("HERMES_VALUATION_SKILL_VERSION", "1.0.0")

        service = ValuationService(tmp_path / "valuation_reports.json")
        manager = RefreshJobManager(tmp_path / "jobs")
        stocks = {"000001": stock()}

        def submit_fn(cfg, prompt, key):
            return "run-1"

        def poll_fn(cfg, run_id):
            return fake_report("000001", "样本", skill_version="0.9.0")

        async def scenario():
            job = service.submit_valuation(["000001"], CFG, stocks, "2026-09-30", manager, {},
                                           submit_fn, poll_fn)
            await manager.close(timeout=5)
            return manager.get(job["job_id"])

        job = asyncio.run(scenario())
        assert job["status"] == "failed"
        assert "000001" in job["failed_codes"]
        assert ValuationService(service.reports_path).get_all() == {}

    def test_idempotency_key_includes_version_and_code(self, tmp_path, monkeypatch):
        captured = {}

        def submit_fn(cfg, prompt, key):
            captured["key"] = key
            return "run-1"

        def poll_fn(cfg, run_id):
            return fake_report("000001", "样本")

        monkeypatch.setenv("HERMES_VALUATION_SKILL_VERSION", "1.0.0")
        run_service(tmp_path, ["000001"], {"000001": stock()}, submit_fn, poll_fn)
        assert captured["key"] == "valuation-000001-2026-09-30-1.0.0"

    def test_active_job_appends_new_code(self, tmp_path):
        """任务运行中提交新代码：追加入队（reused=true），最终全部完成。"""
        import threading

        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            runs = {}

            def submit_fn(cfg, prompt, key):
                code = key.split("-")[1]
                runs[key] = code
                return key

            def poll_fn(cfg, run_id):
                code = runs[run_id]
                if code == "000001":
                    gate.wait(5)  # 工作线程阻塞，制造运行中窗口
                    return fake_report("000001", "样本")
                return fake_report("600000", "浦发")

            job1 = service.submit_valuation(["000001"], CFG, {"000001": stock()}, "2026-09-30",
                                            manager, {}, submit_fn, poll_fn)
            for _ in range(100):
                per_code = service.get_per_code()
                if per_code.get("000001", {}).get("state") == "running":
                    break
                await asyncio.sleep(0.05)
            job2 = service.submit_valuation(["600000"], CFG,
                                            {"000001": stock(), "600000": stock(code="600000", name="浦发")},
                                            "2026-09-30", manager, {}, submit_fn, poll_fn)
            assert job2["reused"] is True
            assert job2["job_id"] == job1["job_id"]
            gate.set()
            await manager.close(timeout=5)
            final = manager.get(job1["job_id"])
            return service, final

        service, job = asyncio.run(scenario())
        assert job["status"] == "succeeded"
        saved = ValuationService(service.reports_path).get_all()
        assert set(saved) == {"000001", "600000"}

    def test_duplicate_code_is_idempotent(self, tmp_path):
        import threading

        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            runs = {}

            def submit_fn(cfg, prompt, key):
                runs[key] = key.split("-")[1]
                return key

            def poll_fn(cfg, run_id):
                gate.wait(5)
                return fake_report("000001", "样本")

            job1 = service.submit_valuation(["000001"], CFG, {"000001": stock()}, "2026-09-30",
                                            manager, {}, submit_fn, poll_fn)
            for _ in range(100):
                per_code = service.get_per_code()
                if per_code.get("000001", {}).get("state") in ("queued", "running"):
                    break
                await asyncio.sleep(0.05)
            queued_at = service.get_per_code()["000001"]["queued_at"]
            job2 = service.submit_valuation(["000001"], CFG, {"000001": stock()}, "2026-09-30",
                                            manager, {}, submit_fn, poll_fn)
            assert job2["reused"] is True
            assert job2["job_id"] == job1["job_id"]
            gate.set()
            await manager.close(timeout=5)
            return job1

        asyncio.run(scenario())

    def test_pool_and_config_errors(self, tmp_path):
        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            errors = []
            unconfigured = HermesConfig(base_url="", api_key="", profile="p",
                                        poll_interval=0, timeout=5, max_concurrent=1)
            try:
                service.submit_valuation(["000001"], unconfigured, {"000001": stock()}, "2026-09-30",
                                         manager, {}, lambda *a: "run", lambda *a: "")
            except ValueError as exc:
                errors.append(str(exc))
            try:
                service.submit_valuation(["999999"], CFG, {"000001": stock()}, "2026-09-30", manager, {},
                                         lambda *a: "run", lambda *a: "")
            except ValueError as exc:
                errors.append(str(exc))
            await manager.close(timeout=5)
            return errors

        errors = asyncio.run(scenario())
        assert any("Hermes 未配置" in e for e in errors)
        assert any("不在采集池" in e for e in errors)

    def test_restart_interrupts_job_and_keeps_reports(self, tmp_path):
        """重启（新 manager）把 active job 置 interrupted；已落盘报告保留。"""
        service, job = run_service(tmp_path, ["000001"], {"000001": stock()},
                                   lambda *a: "run-1", lambda *a: fake_report("000001", "样本"))
        manager2 = RefreshJobManager(tmp_path / "jobs")
        # 上一任务已 succeeded，不会被改动；构造一个 active 残留验证恢复逻辑
        stale = dict(job_id="stale", kind="valuation", status="running", codes=["600000"],
                     params={}, total=1, processed=0, succeeded=0, failed=0, remaining=1,
                     failed_codes=[], retry_codes=["600000"], error=None, created_at=job["created_at"],
                     updated_at=job["created_at"], started_at=None, finished_at=None, message="")
        (tmp_path / "jobs" / "stale.json").write_text(json.dumps(stale), encoding="utf-8")
        manager3 = RefreshJobManager(tmp_path / "jobs")
        restored = manager3.get("stale")
        assert restored["status"] == "interrupted"
        assert restored["retry_codes"] == ["600000"]
