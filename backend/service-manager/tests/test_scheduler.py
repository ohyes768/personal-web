"""检查调度与任务去重（A9）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.checker import Checker
from src.checks.common import CheckStore
from src.checks.github import GithubClient, ReleaseStore
from src.discovery import DiscoveryService
from src.jobs import JobContext, JobManager
from src.models import EndpointInput, JobState, RefreshKind, ServiceCreate
from src.registry import Registry
from tests.conftest import FakeReader, container_payload


def build(store, registry, reader, *, intervals=None, github=None, tls_runner=None):
    discovery = DiscoveryService(store, registry, reader)
    checks = CheckStore(store)
    releases = ReleaseStore(store)
    checker = Checker(
        registry=registry,
        discovery=discovery,
        checks=checks,
        releases=releases,
        github=github,
        intervals=intervals
        or {"url": 300, "tls": 43200, "releases": 21600, "docker": 60},
        tls_runner=tls_runner,
    )
    jobs = JobManager(store)
    for kind in (
        RefreshKind.DOCKER,
        RefreshKind.URL,
        RefreshKind.TLS,
        RefreshKind.RELEASES,
        RefreshKind.ALL,
    ):
        jobs.register(kind, checker.run_kind)
    return checker, jobs, discovery


def ok_transport():
    return httpx.MockTransport(lambda request: httpx.Response(200))


def test_docker_job_updates_observation(store, registry) -> None:
    reader = FakeReader([container_payload()])
    checker, jobs, discovery = build(store, registry, reader)
    job, dedup = jobs.create(RefreshKind.DOCKER)
    assert dedup is False
    finished = asyncio.run(jobs.run(job.id))
    assert finished.state is JobState.COMPLETED
    assert finished.counts["succeeded"] == 1
    assert len(discovery.components()) == 1


def test_docker_job_deduplicates(store, registry) -> None:
    checker, jobs, _ = build(store, registry, FakeReader([]))
    first, _ = jobs.create(RefreshKind.DOCKER)
    second, dedup = jobs.create(RefreshKind.DOCKER)
    assert dedup is True
    assert second.id == first.id


def test_docker_rejects_target_id(store, registry) -> None:
    from src.errors import ApiError

    checker, jobs, _ = build(store, registry, FakeReader([]))
    with pytest.raises(ApiError):
        jobs.create(RefreshKind.DOCKER, "some-service")


def test_docker_failure_marks_job_failed(store, registry) -> None:
    reader = FakeReader([])
    reader.fail_with = RuntimeError("boom")
    checker, jobs, _ = build(store, registry, reader)
    job, _ = jobs.create(RefreshKind.DOCKER)
    finished = asyncio.run(jobs.run(job.id))
    assert finished.state is JobState.FAILED


def test_one_target_failure_does_not_block_others(store, registry) -> None:
    reader = FakeReader([])
    checker, jobs, _ = build(store, registry, reader)
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(service.id, EndpointInput(url="https://good.duomi77.cn/"))
    registry.add_endpoint(service.id, EndpointInput(url="https://bad.duomi77.cn/"))

    original = checker._probe_runner

    async def flaky(url, *, expected_ranges=None, config=None):
        if "bad" in url:
            raise RuntimeError("exploded")
        return await original(url, expected_ranges=expected_ranges, config=config)

    checker._probe_runner = flaky
    checker.probe_config = checker.probe_config
    import src.checks.http_probe as hp

    # 直接调用 runner，让 good 走真实 mock transport
    async def run_all():
        return await checker.run_kind(RefreshKind.URL, None, JobContext("j", RefreshKind.URL, None))

    # http_probe 在测试里没有 transport，会真的去连 → 这里改成 patch
    async def patched(url, *, expected_ranges=None, config=None):
        if "bad" in url:
            raise RuntimeError("exploded")
        from src.checks.http_probe import ProbeResult
        from src.models import UrlState

        return ProbeResult(state=UrlState.REACHABLE, status_code=200, method="HEAD")

    checker._probe_runner = patched
    counts = asyncio.run(run_all())
    assert counts["succeeded"] == 1
    assert counts["failed"] == 1


def test_url_check_records_state_and_timestamp(store, registry) -> None:
    reader = FakeReader([])
    checker, _, _ = build(store, registry, reader)
    service = registry.create_service(ServiceCreate(name="a"))
    endpoint = registry.add_endpoint(service.id, EndpointInput(url="https://x.duomi77.cn/"))
    from src.checks.http_probe import ProbeResult
    from src.models import UrlState

    async def fake(url, *, expected_ranges=None, config=None):
        return ProbeResult(state=UrlState.REACHABLE, status_code=200, method="HEAD")

    checker._probe_runner = fake
    outcome = asyncio.run(checker.run_url(endpoint.id))
    assert outcome.check_status.value == "success"
    view = checker.checks.get(target_type="endpoint", target_id=endpoint.id, check_kind="url")
    assert view is not None
    assert view.current_state == "reachable"
    assert view.last_success_at is not None
    assert view.next_due_at is not None


def test_failed_check_keeps_last_success(store, registry) -> None:
    reader = FakeReader([])
    checker, _, _ = build(store, registry, reader)
    service = registry.create_service(ServiceCreate(name="a"))
    endpoint = registry.add_endpoint(service.id, EndpointInput(url="https://x.duomi77.cn/"))
    from src.checks.http_probe import ProbeResult
    from src.models import UrlState

    async def good(url, *, expected_ranges=None, config=None):
        return ProbeResult(state=UrlState.REACHABLE, status_code=200, method="HEAD")

    async def bad(url, *, expected_ranges=None, config=None):
        return ProbeResult(
            state=UrlState.UNREACHABLE, error_code="timeout", error_message="timeout"
        )

    checker._probe_runner = good
    asyncio.run(checker.run_url(endpoint.id))
    first = checker.checks.get(
        target_type="endpoint", target_id=endpoint.id, check_kind="url"
    )
    success_at = first.last_success_at

    checker._probe_runner = bad
    import time

    time.sleep(1.05)  # 时间戳精度到秒：确保 attempt 时间确实前进
    asyncio.run(checker.run_url(endpoint.id))
    second = checker.checks.get(
        target_type="endpoint", target_id=endpoint.id, check_kind="url"
    )
    assert second.check_status.value == "error"
    assert second.current_state == "unreachable"
    assert second.last_success_at == success_at
    assert second.last_attempt_at != success_at
    assert second.payload["status_code"] == 200  # 旧 payload 保留


def test_due_targets_respect_next_due_at(store, registry) -> None:
    reader = FakeReader([])
    checker, _, _ = build(store, registry, reader)
    service = registry.create_service(ServiceCreate(name="a"))
    endpoint = registry.add_endpoint(service.id, EndpointInput(url="https://x.duomi77.cn/"))
    from src.checks.http_probe import ProbeResult
    from src.models import UrlState

    async def good(url, *, expected_ranges=None, config=None):
        return ProbeResult(state=UrlState.REACHABLE, status_code=200, method="HEAD")

    checker._probe_runner = good
    asyncio.run(checker.run_url(endpoint.id))
    now = datetime.now(timezone.utc)
    assert checker.checks.due(target_type="endpoint", check_kind="url", now=now) == []
    later = now + timedelta(seconds=400)
    assert checker.checks.due(target_type="endpoint", check_kind="url", now=later) == [
        endpoint.id
    ]


def test_run_due_updates_heartbeat(store, registry) -> None:
    checker, _, _ = build(store, registry, FakeReader([]))
    asyncio.run(checker.run_due())
    assert store.get_state("checker_heartbeat") is not None


def test_recovery_marks_interrupted(store, registry) -> None:
    checker, jobs, _ = build(store, registry, FakeReader([]))
    job, _ = jobs.create(RefreshKind.URL)
    job2, _ = jobs.create(RefreshKind.DOCKER)
    with store.transaction() as conn:
        conn.execute(
            "UPDATE refresh_jobs SET state = 'running' WHERE id IN (?, ?)",
            (job.id, job2.id),
        )
    recovered = jobs.recover_interrupted()
    assert recovered == 2
    assert jobs.get(job.id).state is JobState.INTERRUPTED


def test_job_prune_removes_old(store, registry) -> None:
    checker, jobs, _ = build(store, registry, FakeReader([]))
    job, _ = jobs.create(RefreshKind.URL)
    with store.transaction() as conn:
        conn.execute(
            "UPDATE refresh_jobs SET created_at = '2020-01-01T00:00:00+00:00' WHERE id = ?",
            (job.id,),
        )
    assert jobs.prune(keep_days=1) == 1


def test_all_kind_runs_url_tls_releases(store, registry, monkeypatch) -> None:
    reader = FakeReader([container_payload()])
    github = GithubClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    checker, jobs, _ = build(store, registry, reader, github=github)
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(service.id, EndpointInput(url="https://x.duomi77.cn/"))
    from src.checks.http_probe import ProbeResult
    from src.checks.tls_probe import TlsResult
    from src.models import TlsState, UrlState

    async def fake(url, *, expected_ranges=None, config=None):
        return ProbeResult(state=UrlState.REACHABLE, status_code=200, method="HEAD")

    checker._probe_runner = fake
    checker._tls_runner = lambda url: TlsResult(
        state=TlsState.VALID, host="x.duomi77.cn", port=443
    )
    counts = asyncio.run(
        checker.run_kind(RefreshKind.ALL, None, JobContext("j", RefreshKind.ALL, None))
    )
    assert counts["succeeded"] >= 2  # url + tls
    assert "releases" not in str(counts.get("failed"))


def test_cancelled_context_skips_targets(store, registry) -> None:
    checker, _, _ = build(store, registry, FakeReader([]))
    service = registry.create_service(ServiceCreate(name="a"))
    registry.add_endpoint(service.id, EndpointInput(url="https://x.duomi77.cn/"))
    ctx = JobContext("j", RefreshKind.URL, None)
    ctx.cancelled.set()
    counts = asyncio.run(checker.run_kind(RefreshKind.URL, None, ctx))
    assert counts["skipped"] == 1
    assert counts["succeeded"] == 0


def test_scheduler_loop_stops_on_event(store, registry) -> None:
    checker, _, _ = build(store, registry, FakeReader([]))

    async def go():
        stop = asyncio.Event()

        async def stopper():
            await asyncio.sleep(0.05)
            stop.set()

        await asyncio.gather(checker.scheduler_loop(stop=stop, tick=0.02), stopper())

    asyncio.run(go())
    assert store.get_state("checker_heartbeat") is not None


def test_aggregate_health_uses_only_components_with_healthcheck() -> None:
    """聚合只统计配了健康检查的组件；一个都没配才是不适用（页面显示 "-"）。"""
    from src.models import ComponentView, HealthState
    from src.status import compute_health

    # 混合：前端没配检查、后端报了健康 → 用后端的状态
    mixed = [
        ComponentView(source_key="a", health=HealthState.HEALTHY),
        ComponentView(source_key="b", health=HealthState.NOT_CONFIGURED),
    ]
    assert compute_health(components=mixed, bound=True) is HealthState.HEALTHY
    # 一个都没配 → 不适用
    none_configured = [
        ComponentView(source_key="a", health=HealthState.NOT_CONFIGURED),
        ComponentView(source_key="b", health=HealthState.NOT_CONFIGURED),
    ]
    assert (
        compute_health(components=none_configured, bound=True)
        is HealthState.NOT_CONFIGURED
    )
    all_ok = [
        ComponentView(source_key="a", health=HealthState.HEALTHY),
        ComponentView(source_key="b", health=HealthState.HEALTHY),
    ]
    assert compute_health(components=all_ok, bound=True) is HealthState.HEALTHY
    broken = [
        ComponentView(source_key="a", health=HealthState.HEALTHY),
        ComponentView(source_key="b", health=HealthState.UNHEALTHY),
    ]
    assert compute_health(components=broken, bound=True) is HealthState.UNHEALTHY
    assert compute_health(components=[], bound=False) is HealthState.UNKNOWN


def test_aggregate_health_ignores_not_required_components() -> None:
    """非 required 组件不参与聚合：可选组件坏了不等于服务坏了。"""
    from src.models import ComponentView, HealthState
    from src.status import compute_health

    components = [
        ComponentView(source_key="core", health=HealthState.HEALTHY, required=True),
        ComponentView(source_key="optional", health=HealthState.UNHEALTHY, required=False),
    ]
    assert compute_health(components=components, bound=True) is HealthState.HEALTHY
