"""quality_service 编排测试（假 Hermes：注入 submit/poll 双函数，不真连）。"""
import asyncio
import json

import pytest

from src.api.models import DividendStock
from src.services.hermes_client import HermesConfig, HermesRunFailed
from src.services.quality_service import (
    QualityService,
    build_prompt,
    build_stock_payload,
    parse_quality_output,
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


def fake_output(code, name, b=4, m=5, i=3, mg=3, f=5, *, bad_weighted=False, bad_stars=False):
    weighted = None if f is None else round(b * 0.25 + m * 0.25 + i * 0.20 + mg * 0.15 + f * 0.15, 2)
    stars = None if f is None else 4
    if bad_weighted:
        weighted = round(weighted + 0.5, 2)
    if bad_stars:
        stars = 5
    return json.dumps({
        "code": code, "name": name,
        "dimensions": {"business": b, "moat": m, "industry": i, "management": mg, "financial": f},
        "weighted_score": weighted, "stars": stars, "boundary": None,
        "summary": "质量尚可", "risks": ["风险一"], "watch_points": [],
        "report_md": "# 基本面评级\n\n## 五维评分\n内容完整",
    }, ensure_ascii=False)


def run_service(tmp_path, codes, stocks, submit_fn, poll_fn, data_date="2026-09-30"):
    async def scenario():
        service = QualityService(tmp_path / "quality_scores.json")
        manager = RefreshJobManager(tmp_path / "jobs")
        job = service.submit_analysis(codes, CFG, stocks, data_date, manager, submit_fn, poll_fn)
        await manager.close(timeout=5)
        return service, manager.get(job["job_id"])
    return asyncio.run(scenario())


class TestParse:
    def test_plain_json(self):
        score = parse_quality_output(fake_output("000001", "样本"), "000001", "样本")
        assert score.stars == 4
        assert score.weighted_score == 4.05
        assert set(score.dimensions) == {"business", "moat", "industry", "management", "financial"}

    def test_fenced_json_parses(self):
        raw = "```json\n" + fake_output("000001", "样本") + "\n```"
        assert parse_quality_output(raw, "000001", "样本").code == "000001"

    def test_prefixed_json_parses(self):
        raw = "评估结果如下：\n" + fake_output("000001", "样本") + "\n以上。"
        assert parse_quality_output(raw, "000001", "样本").stars == 4

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_quality_output("抱歉，我无法完成该任务。", "000001", "样本")

    def test_weighted_score_mismatch_rejected(self):
        with pytest.raises(ValueError):
            parse_quality_output(fake_output("000001", "样本", bad_weighted=True), "000001", "样本")

    def test_stars_mismatch_rejected(self):
        with pytest.raises(ValueError):
            parse_quality_output(fake_output("000001", "样本", bad_stars=True), "000001", "样本")

    def test_dimension_out_of_range_rejected(self):
        raw = fake_output("000001", "样本", b=6)
        with pytest.raises(ValueError):
            parse_quality_output(raw, "000001", "样本")

    def test_unrated_financial_parses(self):
        # v3：金融股 E 维证据不足为 null，整体未评级，派生字段全 null
        score = parse_quality_output(fake_output("600036", "招行", b=3, m=4, i=3, mg=2, f=None), "600036", "招行")
        assert score.dimensions["financial"] is None
        assert score.dimensions["business"] == 3
        assert score.weighted_score is None
        assert score.stars is None
        assert score.boundary is None

    def test_unrated_with_score_rejected(self):
        raw = fake_output("600036", "招行", f=None).replace('"weighted_score": null', '"weighted_score": 2.4')
        with pytest.raises(ValueError, match="必须全为 null"):
            parse_quality_output(raw, "600036", "招行")

    def test_unrated_with_stars_rejected(self):
        raw = fake_output("600036", "招行", f=None).replace('"stars": null', '"stars": 2')
        with pytest.raises(ValueError, match="必须全为 null"):
            parse_quality_output(raw, "600036", "招行")

    def test_rated_with_null_weighted_rejected(self):
        raw = fake_output("000001", "样本").replace('"weighted_score": 4.05', '"weighted_score": null')
        with pytest.raises(ValueError, match="不能为 null"):
            parse_quality_output(raw, "000001", "样本")


class TestPayloadAndPrompt:
    def test_payload_fields_match_skill_contract(self):
        payload = build_stock_payload(stock(sw_level1="银行"))
        assert payload["code"] == "000001"
        assert payload["avg_yield_3y"] == 4.2
        assert payload["sw_level1"] == "银行"
        assert payload["debt_asset_ratio"] is None  # 缺失传 null 由 skill 降档
        assert payload["roe_history"] == [{"year": 2023, "value": 13}, {"year": 2024, "value": 13}, {"year": 2025, "value": 13}]

    def test_prompt_names_skill_and_requires_json(self):
        prompt = build_prompt(build_stock_payload(stock()))
        assert "basic-quality-rating" in prompt
        assert "JSON" in prompt
        assert '"avg_yield_3y": 4.2' in prompt


class TestSubmitAnalysis:
    def test_analysis_duration_is_measured_and_persisted(self, tmp_path, monkeypatch):
        from src.services import quality_service

        clock = [100.0]
        monkeypatch.setattr(quality_service, "monotonic", lambda: clock[0], raising=False)

        def submit_fn(cfg, prompt, key):
            clock[0] += 2.0
            return "run-1"

        def poll_fn(cfg, run_id):
            clock[0] += 153.25
            return fake_output("000001", "样本")

        service, job = run_service(tmp_path, ["000001"], {"000001": stock()}, submit_fn, poll_fn)
        assert job["status"] == "succeeded"
        # Read a fresh instance to verify persistence, not just in-memory state.
        saved = QualityService(service.quality_path).get_all()["000001"]
        assert saved["analysis_duration_seconds"] == 155.25

    def test_two_stocks_complete(self, tmp_path):
        submitted, polls = [], []
        captured = {}

        def submit_fn(cfg, prompt, key):
            submitted.append(key)
            return f"run-{len(submitted)}"

        def poll_fn(cfg, run_id):
            polls.append(run_id)
            code = "000001" if run_id == "run-1" else "600000"
            return fake_output(code, "样本")

        stocks = {"000001": stock(), "600000": stock(code="600000")}
        service, job = run_service(tmp_path, ["000001", "600000"], stocks, submit_fn, poll_fn)

        assert job["status"] == "succeeded"
        assert (job["processed"], job["succeeded"], job["failed"]) == (2, 2, 0)
        assert submitted == ["quality-000001-2026-09-30", "quality-600000-2026-09-30"]
        saved = service.get_all()
        assert set(saved) == {"000001", "600000"}
        record = saved["000001"]
        assert record["stars"] == 4
        assert record["weighted_score"] == 4.05
        assert record["dimensions"]["moat"] == 5
        assert record["data_date"] == "2026-09-30"
        assert record["scored_at"]
        assert record["report_md"].startswith("# 基本面评级")
        per_code = service.get_per_code()
        assert per_code["000001"]["state"] == "completed"
        assert per_code["600000"]["state"] == "completed"
        assert per_code["000001"]["error"] is None

    def test_unrated_stock_saves_and_completes(self, tmp_path):
        service, job = run_service(
            tmp_path, ["000001"], {"000001": stock()},
            lambda cfg, prompt, key: "run-1",
            lambda cfg, run_id: fake_output("000001", "样本", f=None),
        )
        assert job["status"] == "succeeded"
        record = service.get_all()["000001"]
        assert record["stars"] is None
        assert record["weighted_score"] is None
        assert record["dimensions"]["financial"] is None
        assert service.get_per_code()["000001"]["state"] == "completed"

    def test_one_failure_does_not_block_other(self, tmp_path):
        def submit_fn(cfg, prompt, key):
            return key  # 直接用幂等键当 run_id，便于 poll 按股票区分

        def poll_fn(cfg, run_id):
            if run_id.startswith("quality-600000"):
                raise HermesRunFailed("run xx 终态 failed")
            return fake_output("000001", "样本")

        stocks = {"000001": stock(), "600000": stock(code="600000")}
        service, job = run_service(tmp_path, ["000001", "600000"], stocks, submit_fn, poll_fn)

        assert job["status"] == "partial_failed"
        assert job["failed_codes"] == ["600000"]
        assert set(service.get_all()) == {"000001"}
        per_code = service.get_per_code()
        assert per_code["000001"]["state"] == "completed"
        assert per_code["600000"]["state"] == "failed"
        assert "终态 failed" in per_code["600000"]["error"]

    def test_garbage_output_marks_stock_failed(self, tmp_path):
        service, job = run_service(
            tmp_path, ["000001"], {"000001": stock()},
            lambda cfg, prompt, key: "run-1",
            lambda cfg, run_id: "我无法评估该股票。",
        )
        assert job["status"] == "failed"
        assert job["failed_codes"] == ["000001"]
        assert service.get_all() == {}

    def test_unconfigured_rejected_before_job(self, tmp_path):
        from src.services.hermes_client import HermesConfig as C
        bad = C(base_url="", api_key="", profile="p", poll_interval=0, timeout=5, max_concurrent=1)
        service = QualityService(tmp_path / "quality_scores.json")
        manager = RefreshJobManager(tmp_path / "jobs")
        with pytest.raises(ValueError, match="Hermes 未配置"):
            service.submit_analysis(["000001"], bad, {"000001": stock()}, "2026-09-30", manager,
                                    lambda *a: "r", lambda *a: "{}")

    def test_missing_stock_rejected_before_job(self, tmp_path):
        service = QualityService(tmp_path / "quality_scores.json")
        manager = RefreshJobManager(tmp_path / "jobs")
        with pytest.raises(ValueError, match="不在采集池"):
            service.submit_analysis(["999999"], CFG, {"000001": stock()}, "2026-09-30", manager,
                                    lambda *a: "r", lambda *a: "{}")

    def test_active_job_reused(self, tmp_path):
        import threading
        async def scenario():
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            job1 = service.submit_analysis(
                ["000001"], CFG, {"000001": stock()}, "2026-09-30", manager,
                lambda cfg, prompt, key: (gate.wait(120), "run-1")[1],
                lambda cfg, run_id: fake_output("000001", "样本"))
            job2 = service.submit_analysis(
                ["000001"], CFG, {"000001": stock()}, "2026-09-30", manager,
                lambda cfg, prompt, key: "run-2", lambda cfg, run_id: fake_output("000001", "样本"))
            assert job2["job_id"] == job1["job_id"]
            assert job2["reused"] is True
            gate.set()
            await manager.close(timeout=5)
        asyncio.run(scenario())

    def test_active_job_appends_extra_codes(self, tmp_path):
        import threading

        async def scenario():
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            started = threading.Event()

            def submit_fn(cfg, prompt, key):
                started.set()
                assert gate.wait(120)
                return "run-1"

            stocks = {"000001": stock(), "600519": stock(code="600519", name="新股")}

            def submit_by_key(cfg, prompt, key):
                started.set()
                assert gate.wait(120)
                return f"run-{key}"

            def poll_by_run(cfg, run_id):
                if "600519" in run_id:
                    return fake_output("600519", "新股")
                return fake_output("000001", "样本")

            job1 = service.submit_analysis(
                ["000001"], CFG, stocks, "2026-09-30", manager, submit_by_key, poll_by_run)
            assert started.wait(5)
            before = service.get_per_code()
            assert before["000001"]["state"] == "running"
            # 追加受理复用当前任务的执行闭包；此处传入的 fn 不会被采用
            job2 = service.submit_analysis(
                ["600519"], CFG, stocks, "2026-09-30", manager, submit_by_key, poll_by_run)
            after = service.get_per_code()
            # 旧任务与既有状态不受影响；新代码进入队列
            assert after["000001"]["state"] == "running"
            assert after["000001"] == before["000001"]
            # 追加受理后可能仍在队列或已被派发（并发余量足够时立即开跑）
            assert after["600519"]["state"] in ("queued", "running")
            assert job2["job_id"] == job1["job_id"]
            assert job2["reused"] is True
            assert job2["codes"] == ["000001", "600519"]
            gate.set()
            await manager.close(timeout=5)
            final = manager.get(job2["job_id"])
            assert final["status"] == "succeeded"
            assert set(service.get_all()) == {"000001", "600519"}

        asyncio.run(scenario())

    def test_contained_resubmit_reuses_without_ghost_queued(self, tmp_path):
        import threading

        async def scenario():
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            service._items["600000"] = {
                "code": "600000", "name": "丙", "state": "completed", "error": None,
                "queued_at": "2026-09-30T09:00:00+08:00", "started_at": "2026-09-30T09:00:01+08:00",
                "finished_at": "2026-09-30T09:03:00+08:00", "updated_at": "2026-09-30T09:03:00+08:00",
            }
            gate = threading.Event()
            started = threading.Event()
            cfg = HermesConfig(
                base_url="http://nas:8642", api_key="secret", profile="ohyes768",
                poll_interval=0, timeout=5, max_concurrent=1)
            stocks = {
                "000001": stock(),
                "000002": stock(code="000002", name="乙"),
                "600000": stock(code="600000", name="丙"),
            }

            def submit_fn(cfg, prompt, key):
                started.set()
                assert gate.wait(120)
                return "run-1"

            job1 = service.submit_analysis(
                ["000001", "000002"], cfg, stocks, "2026-09-30", manager,
                submit_fn, lambda c, run_id: fake_output("000001", "样本"))
            assert started.wait(5)
            job2 = service.submit_analysis(
                ["000001"], cfg, stocks, "2026-09-30", manager,
                lambda cfg, prompt, key: "run-should-not-start",
                lambda cfg, run_id: fake_output("000001", "样本"))
            after = service.get_per_code()
            assert job2["job_id"] == job1["job_id"]
            assert job2["reused"] is True
            assert after["600000"]["state"] == "completed"
            assert after["000001"]["state"] == "running"
            assert after["000002"]["state"] == "queued"
            assert [code for code, item in after.items() if item["state"] == "queued"] == ["000002"]
            gate.set()
            await manager.close(timeout=5)


class TestQueueAppend:
    """R1/R3：运行中受理新代码入队（FIFO）；重复提交不重复执行、不重置计时。"""

    def test_append_admits_new_code_while_running(self, tmp_path):
        import threading

        async def scenario():
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            started = threading.Event()
            stocks = {"000001": stock(), "600519": stock(code="600519", name="新股")}

            def submit_fn(cfg, prompt, key):
                started.set()
                assert gate.wait(120)
                return f"run-{key}"

            def poll_fn(cfg, run_id):
                if "000001" in run_id:
                    return fake_output("000001", "样本")
                return fake_output("600519", "新股")

            job1 = service.submit_analysis(
                ["000001"], CFG, stocks, "2026-09-30", manager, submit_fn, poll_fn)
            assert started.wait(5)
            # 追加时使用不同的数据日期，验证受理快照逐项生效
            job2 = service.submit_analysis(
                ["600519"], CFG, stocks, "2026-10-08", manager, submit_fn, poll_fn)
            assert job2["job_id"] == job1["job_id"]
            assert job2["reused"] is True
            assert job2["codes"] == ["000001", "600519"]
            assert (job2["total"], job2["remaining"]) == (2, 2)
            live = service.get_per_code()
            assert live["600519"]["state"] in ("queued", "running")
            assert live["600519"]["queued_at"]
            # 受理先于确认落盘：新的 manager 实例从磁盘读到追加结果
            persisted = RefreshJobManager(tmp_path / "jobs").get(job1["job_id"])
            assert persisted["codes"] == ["000001", "600519"]
            assert persisted["total"] == 2
            gate.set()
            await manager.close(timeout=5)
            final = manager.get(job1["job_id"])
            assert final["status"] == "succeeded"
            assert final["processed"] == 2
            scores = service.get_all()
            assert set(scores) == {"000001", "600519"}
            # 600519 使用受理时的数据日期（幂等键与落盘 data_date 逐项快照）
            assert scores["600519"]["data_date"] == "2026-10-08"

        asyncio.run(scenario())

    def test_duplicate_only_submit_reuses_without_resetting(self, tmp_path):
        import threading

        async def scenario():
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            started = threading.Event()
            submit_count = [0]

            def submit_fn(cfg, prompt, key):
                submit_count[0] += 1
                started.set()
                assert gate.wait(120)
                return "run-1"

            stocks = {"000001": stock()}
            service.submit_analysis(
                ["000001"], CFG, stocks, "2026-09-30", manager, submit_fn,
                lambda cfg, run_id: fake_output("000001", "样本"))
            assert started.wait(5)
            before = service.get_per_code()["000001"]
            job2 = service.submit_analysis(
                ["000001"], CFG, stocks, "2026-09-30", manager, submit_fn,
                lambda cfg, run_id: fake_output("000001", "样本"))
            assert job2["reused"] is True
            assert submit_count[0] == 1
            after = service.get_per_code()["000001"]
            # 重复受理不重置时间戳、不重复执行
            assert after == before
            gate.set()
            await manager.close(timeout=5)

        asyncio.run(scenario())

    def test_retry_failed_code_while_active_requeues(self, tmp_path):
        import threading
        import time as time_mod

        async def scenario():
            # max_concurrent=2：000001 与 600000 同时开跑，600000 先失败可被运行中重试
            cfg = HermesConfig(base_url="http://nas:8642", api_key="secret", profile="p",
                               poll_interval=0, timeout=5, max_concurrent=2)
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            attempts = {"600000": 0}
            attempts_lock = threading.Lock()
            stocks = {"000001": stock(), "600000": stock(code="600000", name="乙")}

            def submit_fn(cfg, prompt, key):
                return key

            def poll_fn(cfg, run_id):
                if "600000" in run_id:
                    with attempts_lock:
                        attempts["600000"] += 1
                        first = attempts["600000"] == 1
                    if first:
                        raise HermesRunFailed("run xx 终态 failed")
                    gate.wait(120)
                    return fake_output("600000", "乙")
                assert gate.wait(120)
                return fake_output("000001", "样本")

            job1 = service.submit_analysis(
                ["000001", "600000"], cfg, stocks, "2026-09-30", manager, submit_fn, poll_fn)
            deadline = time_mod.monotonic() + 5
            while time_mod.monotonic() < deadline:
                if service.get_per_code().get("600000", {}).get("state") == "failed":
                    break
                time_mod.sleep(0.02)
            assert service.get_per_code()["600000"]["state"] == "failed"
            # 运行中重试失败的 600000：并入当前任务，total 计为新受理项
            job2 = service.submit_analysis(
                ["600000"], cfg, stocks, "2026-09-30", manager, submit_fn, poll_fn)
            assert job2["reused"] is True
            assert job2["codes"] == ["000001", "600000"]
            assert (job2["total"], job2["remaining"]) == (3, 2)
            assert service.get_per_code()["600000"]["state"] == "queued"
            gate.set()
            await manager.close(timeout=5)
            final = manager.get(job1["job_id"])
            # 重试成功后失败清单清空，任务以成功收尾
            assert final["status"] == "succeeded"
            assert final["failed_codes"] == []
            assert (final["processed"], final["succeeded"]) == (3, 2)
            assert set(service.get_all()) == {"000001", "600000"}

        asyncio.run(scenario())

    def test_dispatch_follows_fifo_order(self, tmp_path):
        import threading

        async def scenario():
            cfg = HermesConfig(base_url="http://nas:8642", api_key="secret", profile="p",
                               poll_interval=0, timeout=5, max_concurrent=1)
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            order = []
            order_lock = threading.Lock()

            def submit_fn(cfg, prompt, key):
                return key

            def poll_fn(cfg, run_id):
                with order_lock:
                    order.append(run_id)
                return fake_output("000001", "样本")

            stocks = {c: stock(code=c, name=n) for c, n in
                      [("000001", "甲"), ("600000", "乙"), ("600519", "丙")]}
            codes = ["000001", "600000", "600519"]
            service.submit_analysis(codes, cfg, stocks, "2026-09-30", manager, submit_fn, poll_fn)
            await manager.close(timeout=5)
            with order_lock:
                assert order == [f"quality-{c}-2026-09-30" for c in codes]

        asyncio.run(scenario())

    def test_global_concurrency_respected(self, tmp_path):
        import threading
        import time as time_mod

        async def scenario():
            cfg = HermesConfig(base_url="http://nas:8642", api_key="secret", profile="p",
                               poll_interval=0, timeout=5, max_concurrent=2)
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            stats = {"running": 0, "peak": 0}
            stats_lock = threading.Lock()
            codes = ["000001", "000002", "600000", "600519", "601318"]
            stocks = {c: stock(code=c, name=f"股{i}") for i, c in enumerate(codes)}

            def submit_fn(cfg, prompt, key):
                return key

            def poll_fn(cfg, run_id):
                with stats_lock:
                    stats["running"] += 1
                    stats["peak"] = max(stats["peak"], stats["running"])
                time_mod.sleep(0.05)
                with stats_lock:
                    stats["running"] -= 1
                return fake_output("000001", "样本")

            service.submit_analysis(codes, cfg, stocks, "2026-09-30", manager, submit_fn, poll_fn)
            await manager.close(timeout=10)
            assert 1 <= stats["peak"] <= 2

        asyncio.run(scenario())

    def test_fresh_service_waits_for_active_job_then_starts_new(self, tmp_path):
        """跨实例（如重启后新实例）在旧任务收尾前提交：等待终态后开新任务，不丢受理。"""
        import threading
        import time as time_mod

        async def scenario():
            service = QualityService(tmp_path / "quality_scores.json")
            manager = RefreshJobManager(tmp_path / "jobs")
            gate = threading.Event()
            started = threading.Event()
            stocks = {"000001": stock(), "600519": stock(code="600519", name="新股")}

            def submit_fn(cfg, prompt, key):
                started.set()
                assert gate.wait(120)
                return f"run-{key}"

            def poll_fn(cfg, run_id):
                if "000001" in run_id:
                    return fake_output("000001", "样本")
                return fake_output("600519", "新股")

            job1 = service.submit_analysis(
                ["000001"], CFG, stocks, "2026-09-30", manager, submit_fn, poll_fn)
            assert started.wait(5)

            fresh = QualityService(tmp_path / "quality_scores.json")
            result = {}

            def delayed():
                result["job"] = fresh.submit_analysis(
                    ["600519"], CFG, stocks, "2026-09-30", manager, submit_fn, poll_fn)

            worker = threading.Thread(target=delayed, daemon=True)
            worker.start()
            time_mod.sleep(0.3)
            assert worker.is_alive()  # 旧任务收尾前保持等待，不并发受理
            gate.set()
            worker.join(10)
            assert not worker.is_alive()
            job2 = result["job"]
            assert job2["job_id"] != job1["job_id"]
            await manager.close(timeout=5)
            assert set(service.get_all()) == {"000001", "600519"}
            # per_code 是服务内存态：600519 由 fresh 实例受理，状态在 fresh 里
            assert fresh.get_per_code()["600519"]["state"] == "completed"

        asyncio.run(scenario())

        asyncio.run(scenario())
