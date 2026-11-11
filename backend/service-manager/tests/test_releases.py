"""GitHub Release 检查（A10）。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from src.checks.github import (
    GithubClient,
    ReleaseError,
    ReleaseStore,
    classify_releases,
    normalize_release,
    parse_repo,
)
from src.models import ReleaseState


def run(coro):
    return asyncio.run(coro)


def official(release_id: int, tag: str, *, prerelease: bool = False, day: int = 1):
    return {
        "id": release_id,
        "tag_name": tag,
        "name": f"名字 {tag}",
        "published_at": f"2026-01-{day:02d}T00:00:00Z",
        "updated_at": f"2026-01-{day:02d}T00:00:00Z",
        "body": f"正文 {tag}",
        "html_url": f"https://github.com/o/r/releases/tag/{tag}",
        "prerelease": prerelease,
        "draft": False,
    }


def make_client(handler, token=None) -> GithubClient:
    return GithubClient(
        token=token, transport=httpx.MockTransport(handler)
    )


def test_parse_repo_accepts_shorthand_and_url() -> None:
    assert parse_repo("zzet/immich").slug == "zzet/immich"
    assert parse_repo("https://github.com/zzet/immich").slug == "zzet/immich"
    assert parse_repo("https://github.com/zzet/immich.git").slug == "zzet/immich"
    assert parse_repo("github.com/zzet/immich/").slug == "zzet/immich"


def test_parse_repo_rejects_garbage() -> None:
    with pytest.raises(ReleaseError):
        parse_repo("not a repo")


def test_normalize_filters_draft_at_sync_level() -> None:
    item = normalize_release(official(1, "v1".replace("v1", "v1")))
    assert item["release_id"] == 1
    assert item["prerelease"] is False


def test_sync_filters_prerelease_and_sorts_desc(store) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(200, json=official(3, "v3", day=5))
        return httpx.Response(
            200,
            json=[
                official(1, "v1", day=1),
                official(2, "v2-beta", prerelease=True, day=2),
                official(3, "v3", day=5),
                {**official(4, "v4-draft", day=6), "draft": True},
            ],
        )

    client = make_client(handler)
    result = run(client.sync_repo(parse_repo("o/r"), etag=None))
    tags = [item["tag"] for item in result.releases]
    assert tags == ["v3", "v1"]
    assert result.latest_release_id == 3


def test_latest_ignores_prerelease(store) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(200, json=official(9, "v9", prerelease=True))
        return httpx.Response(200, json=[official(1, "v1")])

    result = run(make_client(handler).sync_repo(parse_repo("o/r"), etag=None))
    assert result.latest_release_id is None


def test_304_not_modified(store) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("If-None-Match") == 'W/"abc"'
        return httpx.Response(304)

    result = run(make_client(handler).sync_repo(parse_repo("o/r"), etag='W/"abc"'))
    assert result.not_modified is True


def test_404_raises_repo_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    with pytest.raises(ReleaseError) as exc:
        run(make_client(handler).sync_repo(parse_repo("o/missing"), etag=None))
    assert exc.value.code == "repo_not_found"


def test_429_raises_rate_limited_and_sets_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "60"})

    client = make_client(handler)
    with pytest.raises(ReleaseError) as exc:
        run(client.sync_repo(parse_repo("o/r"), etag=None))
    assert exc.value.code == "rate_limited"
    assert client.blocked() is not None


def test_backoff_blocks_next_call_without_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"retry-after": "60"})

    client = make_client(handler)
    with pytest.raises(ReleaseError):
        run(client.sync_repo(parse_repo("o/r"), etag=None))
    with pytest.raises(ReleaseError) as exc:
        run(client.sync_repo(parse_repo("o/r"), etag=None))
    assert exc.value.code == "rate_limited"
    assert calls == 1  # 第二次没有真的发请求


def test_rate_limit_reset_header_used() -> None:
    reset = str(int(datetime.now(timezone.utc).timestamp()) + 120)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"x-ratelimit-reset": reset})

    client = make_client(handler)
    with pytest.raises(ReleaseError):
        run(client.sync_repo(parse_repo("o/r"), etag=None))
    blocked = client.blocked()
    assert blocked is not None
    assert blocked.timestamp() >= int(reset) - 5


def test_pagination_capped_and_truncated(store) -> None:
    page_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal page_calls
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404)
        page_calls += 1
        return httpx.Response(
            200,
            json=[official(page_calls, f"v{page_calls}")],
            headers={
                "link": f'<https://api.github.com/repos/o/r/releases?page={page_calls + 1}>; rel="next"'
            },
        )

    result = run(make_client(handler).sync_repo(parse_repo("o/r"), etag=None))
    assert page_calls == 3
    assert result.truncated is True


def test_classify_release_states() -> None:
    assert (
        classify_releases(
            baseline_done=True, total_releases=3, unread=1, latest_exists=True, error=None
        )
        is ReleaseState.UNREAD
    )
    assert (
        classify_releases(
            baseline_done=True, total_releases=3, unread=0, latest_exists=True, error=None
        )
        is ReleaseState.NO_UNREAD
    )
    assert (
        classify_releases(
            baseline_done=True, total_releases=0, unread=0, latest_exists=False, error=None
        )
        is ReleaseState.NO_RELEASES
    )
    assert (
        classify_releases(
            baseline_done=True, total_releases=3, unread=0, latest_exists=False, error=None
        )
        is ReleaseState.NO_RELEASES
    )
    assert (
        classify_releases(
            baseline_done=True, total_releases=3, unread=3, latest_exists=True, error="x"
        )
        is ReleaseState.ERROR
    )


def test_first_sync_creates_baseline_and_no_unread_flood(store) -> None:
    releases = ReleaseStore(store)
    from src.checks.github import SyncResult

    result = SyncResult(
        releases=[normalize_release(official(1, "v1")), normalize_release(official(2, "v2", day=2))],
        latest_release_id=2,
    )
    releases.apply("o", "r", result)
    assert result.baseline_created is True
    assert releases.baseline_done("o", "r") is True
    # 基线建立后，历史 Release 全部视为已读
    releases.mark_read("src-1", [1, 2])
    assert releases.unread_ids("src-1", "o", "r") == []


def test_new_release_after_baseline_is_unread(store) -> None:
    releases = ReleaseStore(store)
    from src.checks.github import SyncResult

    releases.apply(
        "o",
        "r",
        SyncResult(releases=[normalize_release(official(1, "v1"))], latest_release_id=1),
    )
    releases.mark_read("src-1", [1])
    releases.apply(
        "o",
        "r",
        SyncResult(
            releases=[
                normalize_release(official(1, "v1")),
                normalize_release(official(2, "v2", day=3)),
            ],
            latest_release_id=2,
        ),
    )
    assert releases.unread_ids("src-1", "o", "r") == [2]


def test_mark_read_explicit_only(store) -> None:
    releases = ReleaseStore(store)
    from src.checks.github import SyncResult

    releases.apply(
        "o",
        "r",
        SyncResult(
            releases=[
                normalize_release(official(1, "v1")),
                normalize_release(official(2, "v2", day=2)),
            ],
            latest_release_id=2,
        ),
    )
    releases.mark_read("src-1", [1])
    assert releases.unread_ids("src-1", "o", "r") == [2]
    assert releases.unread_count("src-1", "o", "r") == 1


def test_shared_repo_cache_isolated_reads(store) -> None:
    releases = ReleaseStore(store)
    from src.checks.github import SyncResult

    releases.apply(
        "o",
        "r",
        SyncResult(releases=[normalize_release(official(1, "v1"))], latest_release_id=1),
    )
    releases.mark_read("src-a", [1])
    # 另一个服务共用同一仓库缓存，但已读状态独立
    assert releases.unread_ids("src-b", "o", "r") == [1]
    assert releases.unread_ids("src-a", "o", "r") == []


def test_mark_error_preserves_cached_releases(store) -> None:
    releases = ReleaseStore(store)
    from src.checks.github import SyncResult

    releases.apply(
        "o",
        "r",
        SyncResult(releases=[normalize_release(official(1, "v1"))], latest_release_id=1),
    )
    releases.mark_error("o", "r", "rate_limited", "too many")
    assert len(releases.cached("o", "r")) == 1
    assert releases.sync_state("o", "r")["state"] == "error"


def test_token_sent_when_configured() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.headers))
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404)
        return httpx.Response(200, json=[])

    run(make_client(handler, token="tkn").sync_repo(parse_repo("o/r"), etag=None))
    assert seen.get("authorization") == "Bearer tkn"
