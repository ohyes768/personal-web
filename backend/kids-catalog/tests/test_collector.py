"""collect_latest 汇总层测试：三路采集去重后统一附曲目总数。"""
import pytest

from src.collector import collect_latest
from src.ximalaya import CredentialsMissing

ROW = {
    "platform": "蜻蜓FM", "album_id": "1", "title": "摇篮曲",
    "url": "https://example.invalid/vchannels/1/", "age_evidence": "蜻蜓FM年龄筛选",
    "age_confidence": "高", "sale_type": 0,
}


@pytest.fixture
def only_qingting(monkeypatch):
    """只留蜻蜓一路采集：官方路径按未配置凭据跳过，喜马拉雅网页路径按不可用跳过。"""
    def no_credentials():
        raise CredentialsMissing("需要环境变量 XM_APP_KEY 与 XM_APP_SECRET")

    def web_unavailable():
        raise RuntimeError("网页采集不可用")

    monkeypatch.setattr("src.collector.XimalayaClient.from_env", no_credentials)
    monkeypatch.setattr("src.collector.collect_qingting", lambda: [dict(ROW)])
    monkeypatch.setattr("src.collector.collect_ximalaya_web", web_unavailable)


def test_collect_latest_attaches_track_count(only_qingting, monkeypatch):
    totals = {"蜻蜓FM": 42}
    monkeypatch.setattr("src.collector.track_total",
                        lambda platform, album_id: totals[platform])
    rows = collect_latest()
    assert rows[0]["track_count"] == 42


def test_collect_latest_track_count_failure_keeps_album(only_qingting, monkeypatch):
    """单张曲目数取不到不阻塞采集：track_count 留空。"""
    def boom(platform, album_id):
        raise RuntimeError("平台接口抖动")

    monkeypatch.setattr("src.collector.track_total", boom)
    rows = collect_latest()
    assert rows[0]["track_count"] is None
