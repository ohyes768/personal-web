"""valuation_service 编排测试（假 Hermes：注入 submit/poll 双函数，不真连）。"""
import asyncio
import json

import pytest

from src.api.models import DividendStock
from src.services.hermes_client import HermesApiError, HermesConfig, HermesRunFailed
from src.services.quality_service import QueueConflict
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


def _wait_until(predicate, timeout=5):
    import time as time_mod
    deadline = time_mod.monotonic() + timeout
    while time_mod.monotonic() < deadline:
        if predicate():
            return
        time_mod.sleep(0.02)
    raise AssertionError("条件未在超时内成立")


# 队列控制测试需要串行调度（同 quality 的 max_concurrent=1）
CFG1 = HermesConfig(base_url=CFG.base_url, api_key=CFG.api_key, profile=CFG.profile,
                    poll_interval=CFG.poll_interval, timeout=CFG.timeout, max_concurrent=1)


class TestQueueControls:
    """取消/调序与 quality 同构：等待项即移除，运行项经 watch 确认 cancelled 才收尾。"""

    def test_waiting_cancel_does_not_submit_and_reorder_is_authoritative(self, tmp_path):
        import threading

        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            release = threading.Event()
            submitted = []

            def submit_fn(cfg, prompt, key):
                submitted.append(key)
                if len(submitted) == 1:
                    assert release.wait(5)
                return key

            def poll_fn(cfg, run_id):
                code = "000001" if "000001" in run_id else "000002" if "000002" in run_id else "600000"
                name = {"000001": "甲", "000002": "乙", "600000": "丙"}[code]
                return fake_report(code, name)

            stocks = {code: stock(code=code, name=name) for code, name in
                      (("000001", "甲"), ("000002", "乙"), ("600000", "丙"))}
            job = service.submit_valuation(
                ["000001", "000002", "600000"], CFG1, stocks, "2026-09-30", manager, {},
                submit_fn, poll_fn)
            _wait_until(lambda: service.get_per_code()["000001"]["state"] == "running"
                        and service.get_per_code()["600000"]["state"] == "queued")
            live = service.get_per_code()
            assert [live["000002"]["position"], live["600000"]["position"]] == [1, 2]
            queued_at = live["600000"]["queued_at"]
            moved = service.move_item(live["600000"]["item_id"], "front", manager)
            assert [moved["per_code"]["600000"]["position"], moved["per_code"]["000002"]["position"]] == [1, 2]
            assert moved["per_code"]["600000"]["queued_at"] == queued_at
            with pytest.raises(QueueConflict, match="已在队首"):
                service.move_item(service.get_per_code()["600000"]["item_id"], "up", manager)
            with pytest.raises(QueueConflict, match="已在队尾"):
                service.move_item(service.get_per_code()["000002"]["item_id"], "down", manager)
            raw = json.loads((tmp_path / "jobs" / f"{job['job_id']}.json").read_text(encoding="utf-8"))
            assert raw["queue_order"] == ["600000", "000002"]
            cancelled_id = service.get_per_code()["000002"]["item_id"]
            service.cancel_item(cancelled_id, manager)
            again = service.cancel_item(cancelled_id, manager)
            assert again["per_code"]["000002"]["state"] == "cancelled"
            assert manager.get(job["job_id"])["cancelled"] == 1
            release.set()
            await manager.close(timeout=5)
            assert all("000002" not in key for key in submitted)
            assert [key.split("-unknown-")[0] for key in submitted] == [
                "valuation-000001-2026-09-30", "valuation-600000-2026-09-30"]
            final = manager.get(job["job_id"])
            assert final["status"] == "succeeded"
            assert final["cancelled"] == 1
            assert final["failed_codes"] == []
            assert "000002" not in service.get_all()

        asyncio.run(scenario())

    def test_stale_attempt_and_readmit_do_not_touch_the_new_item(self, tmp_path):
        import threading

        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            release = threading.Event()

            def submit_fn(cfg, prompt, key):
                if "000001" in key and not release.is_set():
                    assert release.wait(5)
                return key

            stocks = {"000001": stock(), "600000": stock(code="600000", name="乙")}
            service.submit_valuation(
                ["000001", "600000"], CFG1, stocks, "2026-09-30", manager, {}, submit_fn,
                lambda cfg, run_id: fake_report("000001", "样本"))
            _wait_until(lambda: service.get_per_code().get("600000", {}).get("state") == "queued")
            old_id = service.get_per_code()["600000"]["item_id"]
            service.cancel_item(old_id, manager)
            again = service.submit_valuation(
                ["600000"], CFG1, stocks, "2026-09-30", manager, {}, submit_fn,
                lambda cfg, run_id: fake_report("600000", "乙"))
            assert again["reused"] is True
            assert again["total"] == 3
            new_id = service.get_per_code()["600000"]["item_id"]
            assert new_id != old_id
            with pytest.raises(QueueConflict, match="不是当前这一次估值"):
                service.cancel_item(old_id, manager)
            assert service.get_per_code()["600000"]["state"] == "queued"
            with pytest.raises(QueueConflict, match="已开始执行"):
                service.move_item(service.get_per_code()["000001"]["item_id"], "front", manager)
            release.set()
            await manager.close(timeout=5)

        asyncio.run(scenario())

    def test_running_cancel_confirms_via_watch_before_release(self, tmp_path):
        import threading

        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            stops = []
            phase = {"status": "running"}
            polled = threading.Event()

            def stop_fn(cfg, run_id):
                stops.append(run_id)
                phase["status"] = "cancelled"
                return "stopping"

            def get_fn(cfg, run_id):
                polled.set()
                status = phase["status"]
                return {"status": status,
                        "output": fake_report("000001", "样本") if status == "completed" else ""}

            service.submit_valuation(
                ["000001"], CFG1, {"000001": stock()}, "2026-09-30", manager, {},
                lambda cfg, prompt, key: "run-1",
                lambda *args: (_ for _ in ()).throw(AssertionError("不应走阻塞轮询")),
                stop_run_fn=stop_fn, get_run_fn=get_fn)
            assert polled.wait(5)  # 确认已提交到 Hermes，避免走提交前取消分支。
            item_id = service.get_per_code()["000001"]["item_id"]
            pending = service.cancel_item(item_id, manager)
            assert pending["per_code"]["000001"]["state"] == "cancelling"
            _wait_until(lambda: service.get_per_code()["000001"]["state"] == "cancelled")
            assert stops == ["run-1"]
            assert service.get_all() == {}
            await manager.close(timeout=5)
            saved = json.loads(next((tmp_path / "jobs").glob("*.json")).read_text(encoding="utf-8"))
            assert saved["cancelled"] == 1
            assert saved["succeeded"] == 0
            assert saved["failed"] == 0
            assert saved["status"] == "succeeded"
            assert saved["remaining"] == 0

        asyncio.run(scenario())

    def test_completion_beats_cancel_and_keeps_report(self, tmp_path):
        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            stops = []

            def get_fn(cfg, run_id):
                if not stops:
                    return {"status": "running", "output": ""}
                return {"status": "completed", "output": fake_report("000001", "样本")}

            service.submit_valuation(
                ["000001"], CFG1, {"000001": stock()}, "2026-09-30", manager, {},
                lambda *args: "run-1", lambda *args: (_ for _ in ()).throw(AssertionError("poll")),
                stop_run_fn=lambda *args: stops.append("run") or "stopping", get_run_fn=get_fn)
            _wait_until(lambda: service.get_per_code()["000001"]["state"] == "running")
            service.cancel_item(service.get_per_code()["000001"]["item_id"], manager)
            await manager.close(timeout=5)
            assert service.get_per_code()["000001"]["state"] == "completed"
            assert service.get_all()["000001"]["report_md"].startswith("# 四挡位估值")
            saved = json.loads(next((tmp_path / "jobs").glob("*.json")).read_text(encoding="utf-8"))
            assert saved.get("cancelled", 0) == 0
            assert saved["succeeded"] == 1
            assert stops  # stop 已发出，但完成结果优先

        asyncio.run(scenario())

    def test_confirmed_cancel_changes_the_next_idempotency_key(self, tmp_path):
        import threading

        async def scenario():
            service = ValuationService(tmp_path / "valuation_reports.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            keys = []
            release = threading.Event()
            first = {"done": False}

            def submit_fn(cfg, prompt, key):
                keys.append(key)
                if not first["done"]:
                    first["done"] = True
                    assert release.wait(5)
                return key

            def get_fn(cfg, run_id):
                if not release.is_set():
                    return {"status": "running", "output": ""}
                if len(keys) == 1:
                    return {"status": "cancelled", "output": ""}
                return {"status": "completed", "output": fake_report("000001", "样本")}

            def run_once():
                service.submit_valuation(
                    ["000001"], CFG1, {"000001": stock()}, "2026-09-30", manager, {},
                    submit_fn, lambda *args: (_ for _ in ()).throw(AssertionError("poll")),
                    stop_run_fn=lambda *args: "stopping", get_run_fn=get_fn)

            run_once()
            _wait_until(lambda: service.get_per_code()["000001"]["state"] == "running")
            service.cancel_item(service.get_per_code()["000001"]["item_id"], manager)
            release.set()
            _wait_until(lambda: service.get_per_code()["000001"]["state"] == "cancelled")
            run_once()
            await manager.close(timeout=5)
            assert keys[0].startswith("valuation-000001-2026-09-30-")
            assert not keys[0].endswith("-c1")
            assert keys[1].endswith("-c1")

        asyncio.run(scenario())


class TestSessionExport:
    """run_id 落盘与会话 markdown 组装（Hermes 打桩，不真连）"""

    def test_saved_record_contains_run_id(self, tmp_path):
        service, job = run_service(tmp_path, ["000001"], {"000001": stock()},
                                   lambda cfg, prompt, key: "run-runid9",
                                   lambda cfg, run_id: fake_report("000001", "样本"))
        assert job["status"] == "succeeded"
        saved = ValuationService(service.reports_path).get_all()["000001"]
        assert saved["run_id"] == "run-runid9"

    def test_build_session_markdown_renders_summary_and_messages(self):
        from src.services.session_export import build_session_markdown

        def fake_get_session(cfg, run_id):
            return {"session": {
                "model": "test-model", "message_count": 3, "tool_call_count": 2,
                "api_call_count": 2, "input_tokens": 100, "output_tokens": 50,
                "cache_read_tokens": 0, "cache_write_tokens": 0,
                "started_at": 1794389400.0, "ended_at": 1794389460.0,
            }}

        def fake_get_messages(cfg, run_id):
            return [
                {"role": "user", "content": "评估 000001", "timestamp": 1794389400.0},
                {"role": "tool", "tool_name": "terminal", "content": "x" * 10,
                 "timestamp": 1794389405.0},
                {"role": "assistant", "content": [{"type": "text", "text": "结论：ready"}],
                 "timestamp": 1794389460.0},
            ]

        markdown = build_session_markdown(None, "run_x",
                                          get_session_fn=fake_get_session,
                                          get_session_messages_fn=fake_get_messages)
        assert "# Hermes run 会话记录：run_x" in markdown
        assert "test-model" in markdown and "消息数：3" in markdown
        assert "tool: terminal" in markdown
        assert "(+5.0s)" in markdown
        assert "结论：ready" in markdown
