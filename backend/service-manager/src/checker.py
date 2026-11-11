"""检查编排（design §6 调度与手动刷新）。

- 单 worker 后台 asyncio 循环
- 手动/定时刷新共用同一套 runner，因此同一目标不会重复探测
- 一项失败不阻断其他服务；GitHub 遵守全局退避
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from src.checks.common import CheckOutcome, CheckStatus, CheckStore
from src.checks.github import (
    GithubClient,
    ReleaseError,
    ReleaseStore,
    classify_releases,
    outcome_error,
    outcome_success,
    parse_repo,
)
from src.checks.http_probe import ProbeConfig, probe_url, to_outcome
from src.checks.tls_probe import check_certificate, to_outcome as tls_to_outcome
from src.discovery import DiscoveryService
from src.jobs import JobContext
from src.models import RefreshKind, ReleaseState, TlsState, UrlState
from src.registry import Registry

logger = logging.getLogger(__name__)


class ChecksDisabled(RuntimeError):
    pass


class Checker:
    def __init__(
        self,
        *,
        registry: Registry,
        discovery: DiscoveryService,
        checks: CheckStore,
        releases: ReleaseStore,
        github: GithubClient | None = None,
        probe_config: ProbeConfig | None = None,
        intervals: dict[str, int] | None = None,
        tls_runner=None,
        probe_runner=None,
    ) -> None:
        self.registry = registry
        self.discovery = discovery
        self.checks = checks
        self.releases = releases
        self.github = github
        self.probe_config = probe_config or ProbeConfig()
        self.intervals = intervals or {
            "url": 300,
            "tls": 43200,
            "releases": 21600,
            "docker": 60,
        }
        self._tls_runner = tls_runner or check_certificate
        self._probe_runner = probe_runner or probe_url
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 各类检查
    # ------------------------------------------------------------------

    async def run_url(self, endpoint_id: str) -> CheckOutcome:
        endpoint = self._endpoint(endpoint_id)
        target = endpoint.probe_url or endpoint.url
        result = await self._probe_runner(
            target,
            expected_ranges=endpoint.expected_status_ranges,
            config=self.probe_config,
        )
        outcome = to_outcome(result)
        self.checks.record(
            target_type="endpoint",
            target_id=endpoint_id,
            check_kind="url",
            outcome=outcome,
            interval_seconds=self.intervals["url"],
        )
        return outcome

    async def run_tls(self, endpoint_id: str) -> CheckOutcome:
        endpoint = self._endpoint(endpoint_id)
        if not endpoint.url.startswith("https"):
            outcome = CheckOutcome(
                check_status=CheckStatus.ERROR,
                current_state=TlsState.UNKNOWN.value,
                payload={"state": TlsState.UNKNOWN.value},
                error_code="not_https",
                error_message="非 HTTPS 入口不做证书检查",
            )
        else:
            result = await asyncio.to_thread(self._tls_runner, endpoint.url)
            outcome = tls_to_outcome(result)
        self.checks.record(
            target_type="endpoint",
            target_id=endpoint_id,
            check_kind="tls",
            outcome=outcome,
            interval_seconds=self.intervals["tls"],
        )
        return outcome

    async def run_releases(self, service_id: str) -> CheckOutcome:
        source = self.registry.get_release_source_for_service(service_id)
        if source is None:
            outcome = CheckOutcome(
                check_status=CheckStatus.ERROR,
                current_state=ReleaseState.NOT_CONFIGURED.value,
                payload={"state": ReleaseState.NOT_CONFIGURED.value},
                error_code="not_configured",
                error_message="该服务未关联 GitHub 仓库",
            )
        elif self.github is None:
            outcome = outcome_error("github_disabled", "GitHub 检查未启用")
        else:
            try:
                repo = parse_repo(f"{source.owner}/{source.repo}")
                state = self.releases.sync_state(source.owner, source.repo)
                etag = state["etag"] if state else None
                result = await self.github.sync_repo(repo, etag=etag)
                if result.not_modified:
                    cached = self.releases.cached(source.owner, source.repo)
                    unread = len(
                        self.releases.unread_ids(
                            source.id, source.owner, source.repo
                        )
                    )
                    latest = (
                        self.releases.sync_state(source.owner, source.repo) or {}
                    ).get("latest_release_id")
                    outcome = outcome_success(
                        state=classify_releases(
                            baseline_done=True,
                            total_releases=len(cached),
                            unread=unread,
                            latest_exists=latest is not None,
                            error=None,
                        ),
                        count=len(cached),
                        unread=unread,
                        truncated=False,
                        latest_release_id=latest,
                    )
                else:
                    baseline_before = self.releases.baseline_done(
                        source.owner, source.repo
                    )
                    self.releases.apply(source.owner, source.repo, result)
                    if not baseline_before:
                        # 首次成功同步：历史 Release 全部标已读（避免历史未读轰炸）
                        ids = [
                            int(item["release_id"])
                            for item in self.releases.cached(source.owner, source.repo)
                        ]
                        self.releases.mark_read(source.id, ids)
                    unread = len(
                        self.releases.unread_ids(
                            source.id, source.owner, source.repo
                        )
                    )
                    cached = self.releases.cached(source.owner, source.repo)
                    outcome = outcome_success(
                        state=classify_releases(
                            baseline_done=True,
                            total_releases=len(cached),
                            unread=unread,
                            latest_exists=result.latest_release_id is not None,
                            error=None,
                        ),
                        count=len(cached),
                        unread=unread,
                        truncated=result.truncated,
                        latest_release_id=result.latest_release_id,
                    )
            except ReleaseError as exc:
                self.releases.mark_error(
                    source.owner, source.repo, exc.code, exc.message
                )
                outcome = outcome_error(exc.code, exc.message)
        self.checks.record(
            target_type="service",
            target_id=service_id,
            check_kind="releases",
            outcome=outcome,
            interval_seconds=self.intervals["releases"],
        )
        return outcome

    async def run_docker(self) -> CheckOutcome:
        snapshot = await asyncio.to_thread(self.discovery.run_scan)
        if snapshot.ok:
            outcome = CheckOutcome(
                check_status=CheckStatus.SUCCESS,
                current_state="ok",
                payload={
                    "scan_id": snapshot.scan_id,
                    "components": len(snapshot.components),
                    "finished_at": snapshot.finished_at,
                },
            )
        else:
            outcome = CheckOutcome(
                check_status=CheckStatus.ERROR,
                current_state="unknown",
                payload={"error": snapshot.error},
                error_code="docker_unavailable",
                error_message=snapshot.error or "Docker 扫描失败",
            )
        self.checks.record(
            target_type="engine",
            target_id="local",
            check_kind="docker_scan",
            outcome=outcome,
            interval_seconds=self.intervals["docker"],
        )
        return outcome

    # ------------------------------------------------------------------
    # 批量执行（job runner）
    # ------------------------------------------------------------------

    async def run_kind(
        self, kind: RefreshKind, target_id: str | None, ctx: JobContext
    ) -> dict[str, int]:
        counts = {"succeeded": 0, "failed": 0, "skipped": 0}
        async with self._lock:
            if kind == RefreshKind.DOCKER:
                outcome = await self.run_docker()
                if outcome.check_status == CheckStatus.SUCCESS:
                    counts["succeeded"] += 1
                else:
                    counts["failed"] += 1
                return counts

            services = self._service_ids(target_id)
            if kind in (RefreshKind.URL, RefreshKind.ALL):
                for endpoint in self._endpoints(target_id):
                    if ctx.cancelled.is_set():
                        counts["skipped"] += 1
                        continue
                    try:
                        outcome = await self.run_url(endpoint.id)
                        if outcome.check_status == CheckStatus.SUCCESS:
                            counts["succeeded"] += 1
                        else:
                            counts["failed"] += 1
                    except Exception:  # noqa: BLE001 - 单目标失败不阻断
                        logger.exception("url check failed for %s", endpoint.id)
                        counts["failed"] += 1
            if kind in (RefreshKind.TLS, RefreshKind.ALL):
                for endpoint in self._endpoints(target_id):
                    if ctx.cancelled.is_set():
                        counts["skipped"] += 1
                        continue
                    try:
                        outcome = await self.run_tls(endpoint.id)
                        if outcome.check_status == CheckStatus.SUCCESS:
                            counts["succeeded"] += 1
                        else:
                            counts["failed"] += 1
                    except Exception:  # noqa: BLE001
                        logger.exception("tls check failed for %s", endpoint.id)
                        counts["failed"] += 1
            if kind in (RefreshKind.RELEASES, RefreshKind.ALL):
                for service_id in services:
                    if ctx.cancelled.is_set():
                        counts["skipped"] += 1
                        continue
                    source = self.registry.get_release_source_for_service(service_id)
                    if source is None:
                        counts["skipped"] += 1
                        continue
                    try:
                        outcome = await self.run_releases(service_id)
                        if outcome.check_status == CheckStatus.SUCCESS:
                            counts["succeeded"] += 1
                        else:
                            counts["failed"] += 1
                    except Exception:  # noqa: BLE001
                        logger.exception("release check failed for %s", service_id)
                        counts["failed"] += 1
        return counts

    # ------------------------------------------------------------------
    # 调度循环
    # ------------------------------------------------------------------

    async def scheduler_loop(
        self, *, stop: asyncio.Event, tick: float = 15.0
    ) -> None:
        """周期调度：每 tick 检查各目标 next_due_at。"""
        while not stop.is_set():
            try:
                await self.run_due()
            except Exception:  # noqa: BLE001 - 循环不能因单轮失败退出
                logger.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=tick)
            except asyncio.TimeoutError:
                continue

    async def run_due(self, now: datetime | None = None) -> dict[str, int]:
        moment = now or datetime.now(timezone.utc)
        counts = {"url": 0, "tls": 0, "releases": 0}
        if self.intervals.get("docker", 0) > 0:
            due_docker = self.checks.due(
                target_type="engine", check_kind="docker_scan", now=moment
            )
            if due_docker:
                await self.run_docker()
        if self.intervals.get("url", 0) > 0:
            for endpoint_id in self.checks.due(
                target_type="endpoint", check_kind="url", now=moment
            ):
                try:
                    await self.run_url(endpoint_id)
                    counts["url"] += 1
                except Exception:  # noqa: BLE001
                    logger.exception("scheduled url check failed: %s", endpoint_id)
        if self.intervals.get("tls", 0) > 0:
            for endpoint_id in self.checks.due(
                target_type="endpoint", check_kind="tls", now=moment
            ):
                try:
                    await self.run_tls(endpoint_id)
                    counts["tls"] += 1
                except Exception:  # noqa: BLE001
                    logger.exception("scheduled tls check failed: %s", endpoint_id)
        if self.intervals.get("releases", 0) > 0:
            for service_id in self.checks.due(
                target_type="service", check_kind="releases", now=moment
            ):
                try:
                    await self.run_releases(service_id)
                    counts["releases"] += 1
                except Exception:  # noqa: BLE001
                    logger.exception("scheduled release check failed: %s", service_id)
        self.registry.store.set_state(
            "checker_heartbeat", moment.isoformat(timespec="seconds")
        )
        return counts

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _endpoint(self, endpoint_id: str):
        for endpoint in self.registry.list_endpoints():
            if endpoint.id == endpoint_id:
                return endpoint
        from src.errors import not_found

        raise not_found("入口不存在")

    def _endpoints(self, target_id: str | None):
        endpoints = self.registry.list_endpoints(only_enabled=True)
        if target_id:
            return [item for item in endpoints if item.service_id == target_id]
        return endpoints

    def _service_ids(self, target_id: str | None) -> list[str]:
        if target_id:
            return [target_id]
        with self.registry.store.read() as conn:
            rows = conn.execute("SELECT id FROM services").fetchall()
        return [row["id"] for row in rows]
