"""GitHub Release 检查（design §6 Release）。

- 只访问 api.github.com；公开仓库不需要 token
- 每仓库共享缓存、串行请求；ETag 条件请求
- `/releases?per_page=100` 按 Link 分页最多 3 页；过滤 draft 与 prerelease
- `/releases/latest` 单独取 GitHub 标注的最新正式发布
- 第一次成功同步把已获取历史标为已读（避免历史未读轰炸）
- 304 视为检查成功并保持原内容；429/限流遵守 Retry-After / X-RateLimit-Reset
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from src.checks.common import CheckOutcome, CheckStatus
from src.db import Store
from src.models import ReleaseState

API_ROOT = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 3
DEFAULT_TIMEOUT = 15.0

_REPO_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")


class ReleaseError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RepoRef:
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_repo(value: str) -> RepoRef:
    """接受 `owner/repo` 或仓库 URL；只保留公开仓库标识。"""
    text = (value or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        text = text.split("://", 1)[1]
    if text.startswith("github.com/"):
        text = text[len("github.com/") :]
    text = text.strip("/")
    if text.endswith(".git"):
        text = text[: -len(".git")]
    match = _REPO_RE.match(text)
    if not match:
        raise ReleaseError("invalid_repo", "仓库标识应为 owner/repo 或 GitHub 仓库 URL")
    return RepoRef(owner=match.group("owner"), repo=match.group("repo"))


@dataclass
class SyncResult:
    releases: list[dict[str, Any]] = field(default_factory=list)
    latest_release_id: int | None = None
    truncated: bool = False
    not_modified: bool = False
    etag: str | None = None
    baseline_created: bool = False
    new_ids: list[int] = field(default_factory=list)


def _parse_next_link(header: str) -> str | None:
    for part in (header or "").split(","):
        section = part.strip()
        if 'rel="next"' in section:
            start = section.find("<")
            end = section.find(">")
            if start >= 0 and end > start:
                return section[start + 1 : end]
    return None


def normalize_release(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "release_id": int(payload.get("id") or 0),
        "tag": str(payload.get("tag_name") or ""),
        "name": str(payload.get("name") or ""),
        "published_at": payload.get("published_at") or payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
        "body": str(payload.get("body") or ""),
        "html_url": str(payload.get("html_url") or ""),
        "prerelease": bool(payload.get("prerelease")),
    }


class GithubClient:
    """串行、带 ETag 与退避的 GitHub 客户端。"""

    def __init__(
        self,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.token = token
        self.timeout = timeout
        self.transport = transport
        self._blocked_until: datetime | None = None

    def blocked(self, now: datetime | None = None) -> datetime | None:
        moment = now or datetime.now(timezone.utc)
        if self._blocked_until and self._blocked_until > moment:
            return self._blocked_until
        return None

    def _headers(self, etag: str | None) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "service-manager/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if etag:
            headers["If-None-Match"] = etag
        return headers

    async def sync_repo(
        self, repo: RepoRef, *, etag: str | None, now: datetime | None = None
    ) -> SyncResult:
        moment = now or datetime.now(timezone.utc)
        blocked = self.blocked(moment)
        if blocked is not None:
            raise ReleaseError(
                "rate_limited",
                f"GitHub 限流中，{blocked.isoformat(timespec='seconds')} 后重试",
            )
        releases: list[dict[str, Any]] = []
        truncated = False
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            transport=self.transport,
            follow_redirects=False,
        ) as client:
            url: str | None = f"{API_ROOT}/repos/{repo.owner}/{repo.repo}/releases?per_page={PER_PAGE}"
            first = True
            pages = 0
            while url and pages < MAX_PAGES:
                response = await client.get(
                    url, headers=self._headers(etag if first else None)
                )
                self._note_rate_limit(response, moment)
                if first and response.status_code == 304:
                    return SyncResult(not_modified=True, etag=etag)
                if response.status_code == 404:
                    raise ReleaseError("repo_not_found", "仓库不存在或不可公开访问")
                if response.status_code == 429 or response.status_code == 403:
                    raise ReleaseError("rate_limited", "GitHub 拒绝访问（限流或权限）")
                if response.status_code >= 400:
                    raise ReleaseError(
                        "github_error", f"GitHub 返回 {response.status_code}"
                    )
                if first:
                    etag = response.headers.get("etag")
                payload = response.json()
                if not isinstance(payload, list):
                    raise ReleaseError("github_error", "GitHub 响应格式异常")
                for item in payload:
                    if bool(item.get("draft")):
                        continue
                    releases.append(normalize_release(item))
                pages += 1
                next_link = _parse_next_link(response.headers.get("link", ""))
                if next_link and pages >= MAX_PAGES:
                    truncated = True
                url = next_link if pages < MAX_PAGES else None
                first = False

            latest_id: int | None = None
            latest_response = await client.get(
                f"{API_ROOT}/repos/{repo.owner}/{repo.repo}/releases/latest",
                headers=self._headers(None),
            )
            self._note_rate_limit(latest_response, moment)
            if latest_response.status_code == 200:
                data = latest_response.json()
                if isinstance(data, dict) and not data.get("prerelease") and not data.get("draft"):
                    latest_id = int(data.get("id") or 0)
            elif latest_response.status_code not in (404, 403, 429):
                latest_id = None
        stable = [item for item in releases if not item["prerelease"]]
        stable.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        return SyncResult(
            releases=stable,
            latest_release_id=latest_id,
            truncated=truncated,
            etag=etag,
        )

    def _note_rate_limit(self, response: httpx.Response, now: datetime) -> None:
        if response.status_code not in (403, 429):
            return
        reset = response.headers.get("x-ratelimit-reset")
        retry_after = response.headers.get("retry-after")
        until: datetime | None = None
        if retry_after:
            try:
                until = datetime.fromtimestamp(
                    now.timestamp() + float(retry_after), tz=timezone.utc
                )
            except ValueError:
                until = now
        elif reset:
            try:
                until = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            except ValueError:
                until = now
        if until is None:
            until = now
        self._blocked_until = max(until, now)


class ReleaseStore:
    """releases / release_sync / release_reads 持久化。"""

    def __init__(self, store: Store) -> None:
        self.store = store

    def cached(self, owner: str, repo: str) -> list[dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM releases WHERE owner = ? AND repo = ?"
                " ORDER BY published_at DESC",
                (owner, repo),
            ).fetchall()
        return [dict(row) for row in rows]

    def sync_state(self, owner: str, repo: str) -> dict[str, Any] | None:
        with self.store.read() as conn:
            row = conn.execute(
                "SELECT * FROM release_sync WHERE owner = ? AND repo = ?",
                (owner, repo),
            ).fetchone()
        return dict(row) if row else None

    def apply(self, owner: str, repo: str, result: SyncResult) -> list[int]:
        """写入缓存；首次同步建立基线（历史 Release 全标已读）。"""
        with self.store.transaction() as conn:
            state = conn.execute(
                "SELECT * FROM release_sync WHERE owner = ? AND repo = ?",
                (owner, repo),
            ).fetchone()
            baseline_done = bool(state["baseline_done"]) if state else False
            existing = {
                int(row["release_id"])
                for row in conn.execute(
                    "SELECT release_id FROM releases WHERE owner = ? AND repo = ?",
                    (owner, repo),
                ).fetchall()
            }
            new_ids: list[int] = []
            for item in result.releases:
                conn.execute(
                    "INSERT INTO releases(owner, repo, release_id, tag, name,"
                    " published_at, updated_at, body, html_url, prerelease)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(owner, repo, release_id) DO UPDATE SET"
                    " tag = excluded.tag, name = excluded.name,"
                    " published_at = excluded.published_at,"
                    " updated_at = excluded.updated_at, body = excluded.body,"
                    " html_url = excluded.html_url, prerelease = excluded.prerelease",
                    (
                        owner,
                        repo,
                        item["release_id"],
                        item["tag"],
                        item["name"],
                        item["published_at"],
                        item["updated_at"],
                        item["body"],
                        item["html_url"],
                        1 if item["prerelease"] else 0,
                    ),
                )
                if item["release_id"] not in existing:
                    new_ids.append(item["release_id"])
            if not baseline_done:
                result.baseline_created = True
                baseline_done = True
            conn.execute(
                "INSERT INTO release_sync(owner, repo, etag, latest_release_id,"
                " truncated, baseline_done, last_checked_at, state, error)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(owner, repo) DO UPDATE SET etag = excluded.etag,"
                " latest_release_id = excluded.latest_release_id,"
                " truncated = excluded.truncated,"
                " baseline_done = excluded.baseline_done,"
                " last_checked_at = excluded.last_checked_at,"
                " state = excluded.state, error = excluded.error",
                (
                    owner,
                    repo,
                    result.etag,
                    result.latest_release_id,
                    1 if result.truncated else 0,
                    1 if baseline_done else 0,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "ok",
                    None,
                ),
            )
        return new_ids

    def mark_error(self, owner: str, repo: str, code: str, message: str) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO release_sync(owner, repo, state, error, last_checked_at)"
                " VALUES (?,?,?,?,?) ON CONFLICT(owner, repo) DO UPDATE SET"
                " state = excluded.state, error = excluded.error,"
                " last_checked_at = excluded.last_checked_at",
                (
                    owner,
                    repo,
                    "error",
                    f"{code}: {message}",
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )

    def baseline_done(self, owner: str, repo: str) -> bool:
        state = self.sync_state(owner, repo)
        return bool(state and state["baseline_done"])

    def mark_read(self, release_source_id: str, release_ids: list[int]) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.store.transaction() as conn:
            count = 0
            for release_id in release_ids:
                cur = conn.execute(
                    "INSERT INTO release_reads(release_source_id, release_id, read_at)"
                    " VALUES (?,?,?) ON CONFLICT(release_source_id, release_id)"
                    " DO NOTHING",
                    (release_source_id, release_id, now),
                )
                count += cur.rowcount
        return count

    def unread_ids(
        self, release_source_id: str, owner: str, repo: str
    ) -> list[int]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT r.release_id FROM releases r LEFT JOIN release_reads rr"
                " ON rr.release_source_id = ? AND rr.release_id = r.release_id"
                " WHERE r.owner = ? AND r.repo = ? AND rr.release_id IS NULL",
                (release_source_id, owner, repo),
            ).fetchall()
        return [int(row["release_id"]) for row in rows]

    def read_ids(self, release_source_id: str) -> set[int]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT release_id FROM release_reads WHERE release_source_id = ?",
                (release_source_id,),
            ).fetchall()
        return {int(row["release_id"]) for row in rows}

    def releases_for_source(
        self, release_source_id: str, owner: str, repo: str
    ) -> list[dict[str, Any]]:
        read = self.read_ids(release_source_id)
        items = self.cached(owner, repo)
        for item in items:
            item["read"] = int(item["release_id"]) in read
        return items

    def unread_count(self, release_source_id: str, owner: str, repo: str) -> int:
        return len(self.unread_ids(release_source_id, owner, repo))

    def clear_reads(self, release_source_id: str) -> None:
        with self.store.transaction() as conn:
            conn.execute(
                "DELETE FROM release_reads WHERE release_source_id = ?",
                (release_source_id,),
            )


def classify_releases(
    *,
    baseline_done: bool,
    total_releases: int,
    unread: int,
    latest_exists: bool,
    error: str | None,
) -> ReleaseState:
    if error:
        return ReleaseState.ERROR
    if total_releases == 0:
        return ReleaseState.NO_RELEASES
    if not latest_exists:
        return ReleaseState.NO_RELEASES
    if unread > 0:
        return ReleaseState.UNREAD
    return ReleaseState.NO_UNREAD


def outcome_success(
    *,
    state: ReleaseState,
    count: int,
    unread: int,
    truncated: bool,
    latest_release_id: int | None,
) -> CheckOutcome:
    return CheckOutcome(
        check_status=CheckStatus.SUCCESS,
        current_state=state.value,
        payload={
            "state": state.value,
            "release_count": count,
            "unread": unread,
            "truncated": truncated,
            "latest_release_id": latest_release_id,
            "source": "api.github.com",
        },
    )


def outcome_error(code: str, message: str) -> CheckOutcome:
    return CheckOutcome(
        check_status=CheckStatus.ERROR,
        current_state=ReleaseState.ERROR.value,
        payload={"state": ReleaseState.ERROR.value, "error_code": code},
        error_code=code,
        error_message=message,
    )
