"""HermesLimiter 跨 service 并发闸测试（quality + valuation 共享名额）。

验证三件事：全局上限真实生效（两类任务合计 ≤ limit）、信号量等待中的项可被取消、
名额不泄漏。服务注入同一个 limiter 实例，与 main.py 的接线方式一致。
"""
import asyncio
import threading
import time

from src.services.hermes_client import HermesConfig
from src.services.hermes_limiter import HermesLimiter
from src.services.quality_service import QualityService
from src.services.valuation_service import ValuationService
from src.services.refresh_jobs import RefreshJobManager

CFG = HermesConfig(base_url="http://nas:8642", api_key="secret", profile="ohyes768",
                   poll_interval=0, timeout=5, max_concurrent=4)  # 本地不限，全局闸才生效


def q_stock(**updates):
    from src.api.models import DividendStock
    fields = dict(code="000001", name="甲", exchange="深市主板", avg_yield_3y=4.2)
    fields.update(updates)
    return DividendStock(**fields)


def fake_quality_output(code, name):
    import json
    return json.dumps({
        "code": code, "name": name,
        "dimensions": {"business": 3, "moat": 3, "industry": 3, "management": 3, "financial": 3},
        "weighted_score": 3.0, "stars": 3, "boundary": "及格",
        "summary": "一般", "risks": [], "watch_points": [],
        "report_md": "# 基本面评级",
    }, ensure_ascii=False)


def fake_valuation_output(code, name):
    import json
    return json.dumps({
        "schema_version": "1.0.0", "skill_version": "1.0.0", "code": code, "name": name,
        "currency": "CNY", "as_of": "2026-11-11", "status": "ready",
        "levels": {
            "heavy_position": {"price": 10.0, "pe": 5.0, "pb": 0.7},
            "add_position": {"price": 12.0, "pe": 6.0, "pb": 0.8},
            "reduce_position": {"price": 15.0, "pe": 7.5, "pb": 1.0},
            "full_exit": {"price": 19.0, "pe": 9.5, "pb": 1.3},
        },
        "valuation": {"primary_method": "pe_multiple"},
        "evidence": [], "data_gaps": [],
        "confidence": {"level": "medium", "reason": "测试"},
        "risks": [], "invalidation_conditions": [],
        "summary": "测试", "report_md": "# 四挡位估值",
        "analysis": {"business": "b", "normalization": "n", "dividend": "d",
                     "valuation": "v", "risk": "r"},
    }, ensure_ascii=False)


def _wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("条件未在超时内成立")


class TestLimiterBasics:
    def test_acquire_release_accounting(self):
        limiter = HermesLimiter(2)
        assert limiter.acquire(timeout=0.1)
        assert limiter.acquire(timeout=0.1)
        assert limiter.active == 2
        assert not limiter.acquire(timeout=0.05)  # 满了拿不到
        limiter.release()
        assert limiter.active == 1
        assert limiter.acquire(timeout=0.1)
        limiter.release()
        limiter.release()
        assert limiter.active == 0
        limiter.release()  # 过度释放被防御性忽略，不抛错
        assert limiter.active == 0

    def test_limit_floor(self):
        assert HermesLimiter(0).limit == 1
        assert HermesLimiter(-3).limit == 1
        assert HermesLimiter.from_env().limit >= 1


class TestCrossServiceCap:
    def test_quality_and_valuation_share_one_slot(self, tmp_path):
        """quality + valuation 同时各跑一只，全局同时在跑 ≤ limit（此处 limit=1）。"""
        async def scenario():
            limiter = HermesLimiter(1)
            quality = QualityService(tmp_path / "q.json", limiter=limiter)
            valuation = ValuationService(tmp_path / "v.json", limiter=limiter)
            manager = RefreshJobManager(tmp_path / "jobs")
            release = threading.Event()
            lock = threading.Lock()
            stats = {"inflight": 0, "max_seen": 0}

            def tracked_submit(cfg, prompt, key):
                with lock:
                    stats["inflight"] += 1
                    stats["max_seen"] = max(stats["max_seen"], stats["inflight"])
                assert release.wait(5)
                with lock:
                    stats["inflight"] -= 1
                return key

            q_stocks = {"000001": q_stock()}
            v_stocks = {"600000": q_stock(code="600000", name="乙")}
            q_job = quality.submit_analysis(
                ["000001"], CFG, q_stocks, "2026-09-30", manager, tracked_submit,
                lambda cfg, run_id: fake_quality_output("000001", "甲"))
            v_job = valuation.submit_valuation(
                ["600000"], CFG, v_stocks, "2026-09-30", manager, {},
                tracked_submit, lambda cfg, run_id: fake_valuation_output("600000", "乙"))
            _wait_until(lambda: stats["max_seen"] >= 1)
            release.set()
            await manager.close(timeout=5)
            return limiter, manager, q_job, v_job, stats

        limiter, manager, q_job, v_job, stats = asyncio.run(scenario())
        assert stats["max_seen"] == 1  # 两类任务并行，全局仍串行
        assert limiter.active == 0  # 名额全部归还
        assert manager.get(q_job["job_id"])["status"] == "succeeded"
        assert manager.get(v_job["job_id"])["status"] == "succeeded"

    def test_waiting_cancel_releases_no_slot_and_skips_submission(self, tmp_path):
        """信号量被占住时受理的项保持 queued；取消后不消耗名额也不提交 Hermes。"""
        async def scenario():
            limiter = HermesLimiter(1)
            limiter.acquire()  # 外部占住唯一名额
            valuation = ValuationService(tmp_path / "v.json", limiter=limiter)
            manager = RefreshJobManager(tmp_path / "jobs")
            submitted = []

            def submit_fn(cfg, prompt, key):
                submitted.append(key)
                return key

            stocks = {"000001": q_stock()}
            job = valuation.submit_valuation(
                ["000001"], CFG, stocks, "2026-09-30", manager, {}, submit_fn,
                lambda cfg, run_id: fake_valuation_output("000001", "甲"))
            _wait_until(lambda: manager.get(job["job_id"])["status"] == "running")
            assert valuation.get_per_code()["000001"]["state"] == "queued"  # 等名额，不翻 running
            valuation.cancel_item(valuation.get_per_code()["000001"]["item_id"], manager)
            assert valuation.get_per_code()["000001"]["state"] == "cancelled"
            limiter.release()  # 释放后调度循环应收尾，绝不补跑已取消项
            await manager.close(timeout=5)
            return manager.get(job["job_id"]), submitted, limiter

        final, submitted, limiter = asyncio.run(scenario())
        assert submitted == []  # 从未提交 Hermes
        assert final["cancelled"] == 1
        assert final["succeeded"] == 0
        assert final["status"] == "succeeded"
        assert limiter.active == 0

    def test_no_slot_leak_across_repeats(self, tmp_path):
        """连续多轮跑满-释放，名额不泄漏（泄漏会卡死后续项）。"""
        async def scenario():
            limiter = HermesLimiter(1)
            valuation = ValuationService(tmp_path / "v.json", limiter=limiter)
            manager = RefreshJobManager(tmp_path / "jobs")
            stocks = {code: q_stock(code=code, name=name)
                      for code, name in (("000001", "甲"), ("000002", "乙"), ("600000", "丙"))}
            job = valuation.submit_valuation(
                ["000001", "000002", "600000"], CFG, stocks, "2026-09-30", manager, {},
                lambda cfg, prompt, key: key,
                lambda cfg, run_id: fake_valuation_output(run_id.split("-")[1], "样本"))
            await manager.close(timeout=10)
            return manager.get(job["job_id"]), limiter

        final, limiter = asyncio.run(scenario())
        assert final["status"] == "succeeded"
        assert final["succeeded"] == 3
        assert limiter.active == 0
