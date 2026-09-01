"""scheduler job self-call 路径测试。

refresh 接口装饰器是 /dividend/refresh，app 前缀是 /api/dividend，
最终真实路径是 POST /api/dividend/dividend/refresh（与前端 api.ts 一致）。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.scheduler.jobs import refresh_dividend, refresh_m120, refresh_realtime


class _Ctx:
    port = 8092
    jobs_meta = {
        "monthly_dividend": {"params": {"min_dividend": 10}},
        "weekly_m120": {},
        "daily_price_pre": {},
    }

    def get_holdings_codes(self):
        return ["600000"]


def _ok_response(payload=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload or {"count": 1}
    resp.text = ""
    return resp


def _run_self_call(fn, job_id, ctx, mock_post):
    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("src.scheduler.jobs.httpx.AsyncClient", return_value=mock_client):
        return asyncio.run(fn(ctx, job_id))


def test_refresh_dividend_posts_to_double_prefix_path():
    """股息率刷新必须打到 /api/dividend/dividend/refresh，少一层会 404。"""
    mock_post = AsyncMock(return_value=_ok_response())
    result = _run_self_call(refresh_dividend, "monthly_dividend", _Ctx(), mock_post)

    mock_post.assert_awaited_once()
    url, = mock_post.await_args.args
    assert url == "http://127.0.0.1:8092/api/dividend/dividend/refresh"
    assert mock_post.await_args.kwargs["json"] == {"min_dividend": 10}
    assert result["status"] == "success"


def test_refresh_realtime_and_m120_keep_single_prefix_paths():
    mock_post = AsyncMock(return_value=_ok_response())
    _run_self_call(refresh_realtime, "daily_price_pre", _Ctx(), mock_post)
    url, = mock_post.await_args.args
    assert url == "http://127.0.0.1:8092/api/dividend/realtime/refresh"

    mock_post.reset_mock()
    mock_post.return_value = _ok_response()
    _run_self_call(refresh_m120, "weekly_m120", _Ctx(), mock_post)
    url, = mock_post.await_args.args
    assert url == "http://127.0.0.1:8092/api/dividend/m120/refresh"
