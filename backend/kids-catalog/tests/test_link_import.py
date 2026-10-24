import urllib.error

import pytest

from src import link_import
from src.link_import import LinkImportError, parse_album_link, probe_album


def xm_page(tracks, total=10, max_page=1, ret=0, msg=""):
    return {"ret": ret, "msg": msg,
            "data": {"totalCount": total, "maxPageId": max_page, "pageId": 1,
                     "pageSize": 30, "list": tracks}}


def xm_track(album_title="宝宝巴士经典儿歌", paid=False):
    return {"albumTitle": album_title, "title": "某首儿歌", "trackId": 1, "isPaid": paid}


@pytest.mark.parametrize("url", [
    "https://www.ximalaya.com/album/4436043",
    "https://m.ximalaya.com/album/4436043",
    "https://ximalaya.com/album/4436043",
    "https://www.ximalaya.com/album/4436043/",
    "https://www.ximalaya.com/album/4436043?from=search",
    "www.ximalaya.com/album/4436043",
    "  https://www.ximalaya.com/album/4436043  ",
    "https://WWW.Ximalaya.com/Album/4436043",
])
def test_parse_ximalaya_album_link(url):
    assert parse_album_link(url) == ("喜马拉雅", "4436043")


@pytest.mark.parametrize("url,album_id", [
    ("https://m.ximalaya.com/selfshare/albumnew/16350309", "16350309"),
    ("https://m.ximalaya.com/selfshare/album/3715099", "3715099"),
    ("m.ximalaya.com/selfshare/albumnew/16350309", "16350309"),
    ("https://m.ximalaya.com/selfshare/albumnew/16350309/", "16350309"),
    ("https://m.ximalaya.com/selfshare/albumnew/16350309?cId=6&srcId=16350309&tpName=weixin", "16350309"),
])
def test_parse_ximalaya_selfshare_link(url, album_id):
    """微信分享的 selfshare/album(new) 路径与标准 album/{id} 指向同一专辑。"""
    assert parse_album_link(url) == ("喜马拉雅", album_id)


def test_parse_real_wechat_share_links():
    """两条真实分享链接（2026-10-24 用户提供）作回归锚点。"""
    u1 = ("https://m.ximalaya.com/selfshare/albumnew/16350309?cId=6&uid=72626596"
          "&shrdv=XICzu1Lac649xvIRiMla8G_6lC7giqDxX90&shrh5=iphone&shrid=1a16912037b9ffa"
          "&shrdh=1&shrpid=1a16912037b9002&srcType=6&subType=1010&srcId=16350309&tpName=weixin"
          "&commandShareId=75e49d7bfb85001886f897ebb5d0d4b9&shareTime=1792764150651&shareLevel=1")
    u2 = ("https://m.ximalaya.com/selfshare/album/3715099?cId=6&uid=72626596"
          "&shrdv=XICzu1Lac649xvIRiMla8G_6lC7giqDxX90&shrh5=iphone&shrid=1a1691247791331d"
          "&shrdh=1&shrpid=1a169124779ca1&srcType=6&subType=1010&srcId=3715099&tpName=weixin"
          "&commandShareId=e7596f85275246ffbd3dbf6117f1bf5b&shareTime=1792764168057&shareLevel=1")
    assert parse_album_link(u1) == ("喜马拉雅", "16350309")
    assert parse_album_link(u2) == ("喜马拉雅", "3715099")


@pytest.mark.parametrize("url", [
    "https://www.qingting.fm/vchannels/326665",
    "https://m.qingting.fm/vchannels/326665",
    "https://m.qingting.fm/vchannels/326665/",
    "https://www.qingting.fm/vchannels/326665?tab=all",
    "m.qingting.fm/vchannels/326665",
])
def test_parse_qingting_album_link(url):
    assert parse_album_link(url) == ("蜻蜓FM", "326665")


@pytest.mark.parametrize("url", [
    "https://www.ximalaya.com/sound/959103846",
    "https://www.ximalaya.com/radio/959103846",
    "https://www.ximalaya.com/album/4436043abc",
    "https://example.com/album/1",
    "",
])
def test_parse_rejects_unsupported_links(url):
    """单曲/无关链接一律拒绝，不静默入库。"""
    with pytest.raises(LinkImportError):
        parse_album_link(url)


def test_probe_ximalaya_free_album(monkeypatch):
    monkeypatch.setattr(link_import, "_fetch_json",
                        lambda url, referer=None: xm_page([xm_track()], total=864, max_page=29))
    result = probe_album("喜马拉雅", "4436043")
    assert result["title"] == "宝宝巴士经典儿歌"
    assert result["track_count"] == 864
    assert result["sale_type"] == 0


def test_probe_ximalaya_whole_paid_album_is_rejected(monkeypatch):
    """整张付费：首页与末页全是 isPaid → 拒绝导入。"""
    monkeypatch.setattr(link_import, "_fetch_json",
                        lambda url, referer=None: xm_page([xm_track(paid=True)], total=143, max_page=5))
    with pytest.raises(LinkImportError, match="付费专辑不支持下载"):
        probe_album("喜马拉雅", "15746968")


def test_probe_ximalaya_mixed_album_is_allowed(monkeypatch):
    """真假混合：属于免费专辑，允许导入，下载时逐条跳过受限曲目。"""
    monkeypatch.setattr(link_import, "_fetch_json",
                        lambda url, referer=None: xm_page([xm_track(paid=True), xm_track(paid=False)]))
    assert probe_album("喜马拉雅", "123")["track_count"] == 10


def test_probe_ximalaya_paid_first_page_but_free_last_page_is_allowed(monkeypatch):
    """首页恰好全付费、末页有免费曲 → 复核后放行，不误判为整张付费。"""

    def fake(url, referer=None):
        if "pageId=1" in url:
            return xm_page([xm_track(paid=True)], total=60, max_page=2)
        return xm_page([xm_track(paid=False)], total=60, max_page=2)

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    assert probe_album("喜马拉雅", "123")["title"] == "宝宝巴士经典儿歌"


def test_probe_ximalaya_offline_album_is_rejected(monkeypatch):
    """新旧接口都报 924 才判真下架。"""
    monkeypatch.setattr(link_import, "_fetch_json",
                        lambda url, referer=None: {"ret": 924, "msg": "亲，该内容因故已下架，请您谅解"})
    with pytest.raises(LinkImportError, match="已下架"):
        probe_album("喜马拉雅", "999")


def xm_single_page(album_title, tracks, total=None, max_page=1):
    """旧接口 album/single 的响应形状（2026-10-24 实测）。"""
    return {"ret": 0, "msg": "0", "data": {
        "album": {"title": album_title},
        "tracks": {"list": tracks, "pageId": 1, "pageSize": 30,
                   "totalCount": len(tracks) if total is None else total,
                   "maxPageId": max_page}}}


def test_probe_ximalaya_offline_album_falls_back_to_single_api(monkeypatch):
    """新版接口报下架(ret=924)、旧接口仍在服务（2026-10-24 实测）：预检取到专辑信息，不误报下架。"""

    def fake(url, referer=None):
        if "album/single" in url:
            return xm_single_page("听，小蜗牛艾玛",
                                  [{"trackId": 98082355, "title": "完整版", "isPaid": False}], total=18)
        return {"ret": 924, "msg": "亲，该内容因故已下架，请您谅解"}

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    result = probe_album("喜马拉雅", "16350309")
    assert result["title"] == "听，小蜗牛艾玛"
    assert result["track_count"] == 18
    assert result["sale_type"] == 0


def test_probe_ximalaya_whole_paid_via_single_fallback_is_rejected(monkeypatch):
    """兜底路径同样执行付费判定：旧接口全付费 → 拒绝导入。"""

    def fake(url, referer=None):
        if "album/single" in url:
            return xm_single_page("付费专辑", [{"trackId": 1, "title": "某集", "isPaid": True}])
        return {"ret": 924, "msg": "已下架"}

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    with pytest.raises(LinkImportError, match="付费专辑不支持下载"):
        probe_album("喜马拉雅", "1")


def test_probe_ximalaya_network_failure_is_reported(monkeypatch):
    """网络故障如实报错，让用户重试，而不是抛出未捕获异常。"""

    def fake(url, referer=None):
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    with pytest.raises(LinkImportError, match="网络请求失败"):
        probe_album("喜马拉雅", "123")


def test_probe_ximalaya_malformed_payload_is_rejected(monkeypatch):
    """接口返回空 data：如实报错，不抛未捕获异常。"""
    monkeypatch.setattr(link_import, "_fetch_json", lambda url, referer=None: {"ret": 0, "data": None})
    with pytest.raises(LinkImportError, match="接口返回异常"):
        probe_album("喜马拉雅", "123")


def test_probe_ximalaya_empty_track_list_is_rejected(monkeypatch):
    """专辑有 totalCount 但取不到曲目：拒绝导入，不建 0 曲的目录行。"""
    monkeypatch.setattr(link_import, "_fetch_json",
                        lambda url, referer=None: {"ret": 0, "data": {"totalCount": 10, "list": []}})
    with pytest.raises(LinkImportError, match="没有可读取的曲目"):
        probe_album("喜马拉雅", "123")


def test_probe_ximalaya_missing_title_is_rejected(monkeypatch):
    """取不到专辑名：拒绝导入，目录行不能没有标题。"""
    monkeypatch.setattr(link_import, "_fetch_json", lambda url, referer=None: xm_page(
        [{"trackId": 1, "title": "某首儿歌", "isPaid": False}]))
    with pytest.raises(LinkImportError, match="未能读取到专辑名称"):
        probe_album("喜马拉雅", "123")


def test_probe_ximalaya_http_error_is_reported(monkeypatch):
    def fake(url, referer=None):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    with pytest.raises(LinkImportError, match="HTTP 503"):
        probe_album("喜马拉雅", "123")


def test_probe_qingting_free_channel(monkeypatch):
    def fake(url, referer=None):
        if "capi/v3/channel/" in url:
            return {"data": {"id": 326665, "v": "abc", "title": "宝宝巴士·三字儿歌"}}
        return {"data": {"total": 91, "programs": [{"id": 1, "title": "某集"}]}}

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    result = probe_album("蜻蜓FM", "326665")
    assert result["title"] == "宝宝巴士·三字儿歌"
    assert result["track_count"] == 91


def test_probe_qingting_vip_channel_is_rejected(monkeypatch):
    """会员专辑：专辑级 vip_label=会员畅听 → 整张付费，拒绝导入。"""
    monkeypatch.setattr(link_import, "_fetch_json", lambda url, referer=None: {
        "data": {"id": 464506, "v": "abc", "title": "神奇的朋友", "vip_label": "会员畅听"}})
    with pytest.raises(LinkImportError, match="付费专辑不支持下载"):
        probe_album("蜻蜓FM", "464506")


def test_probe_qingting_missing_version_is_rejected(monkeypatch):
    """缺版本号拿不到节目列表，如实报错而不是给一个 0 曲的目录行。"""
    monkeypatch.setattr(link_import, "_fetch_json", lambda url, referer=None: {
        "data": {"id": 326665, "title": "宝宝巴士·三字儿歌"}})
    with pytest.raises(LinkImportError, match="未能读取到蜻蜓专辑信息"):
        probe_album("蜻蜓FM", "326665")


def test_probe_qingting_other_http_error_is_reported(monkeypatch):
    def fake(url, referer=None):
        raise urllib.error.HTTPError(url, 500, "Server Error", None, None)

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    with pytest.raises(LinkImportError, match="HTTP 500"):
        probe_album("蜻蜓FM", "326665")


def test_probe_qingting_network_failure_is_reported(monkeypatch):
    """网络故障如实报错让用户重试，不抛未捕获异常。"""

    def fake(url, referer=None):
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    with pytest.raises(LinkImportError, match="网络请求失败"):
        probe_album("蜻蜓FM", "326665")


def test_probe_qingting_vip_label_variant_is_rejected(monkeypatch):
    """平台换文案（会员专享）同样按会员专辑拒绝。"""
    monkeypatch.setattr(link_import, "_fetch_json", lambda url, referer=None: {
        "data": {"id": 464506, "v": "abc", "title": "神奇的朋友", "vip_label": "会员专享"}})
    with pytest.raises(LinkImportError, match="付费专辑不支持下载"):
        probe_album("蜻蜓FM", "464506")


def test_probe_qingting_missing_channel_is_rejected(monkeypatch):
    def fake(url, referer=None):
        raise urllib.error.HTTPError(url, 400, "Bad Request", None, None)

    monkeypatch.setattr(link_import, "_fetch_json", fake)
    with pytest.raises(LinkImportError, match="未找到该蜻蜓专辑"):
        probe_album("蜻蜓FM", "999999999")


def test_probe_qingting_empty_channel_data_is_rejected(monkeypatch):
    """专辑接口返回空 data：拒绝导入，不建 0 曲的目录行。"""
    monkeypatch.setattr(link_import, "_fetch_json", lambda url, referer=None: {"data": None})
    with pytest.raises(LinkImportError, match="未找到该蜻蜓专辑"):
        probe_album("蜻蜓FM", "999999999")


def test_probe_rejects_unknown_platform():
    with pytest.raises(LinkImportError):
        probe_album("荔枝FM", "1")
