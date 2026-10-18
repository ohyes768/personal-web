import json
import threading

import pytest

from src.services.fang_request_policy import FangRequestPolicy, FangChallenge, FangCoolingDown, FangRequestCancelled, FangTemporarilyUnavailable
from src.services.fang_detail_cache import FangDetailCache
from src.services.fang_rentals import crawl, crawl_runs


class Clock:
    def __init__(self):
        self.now = 100000.0
        self.waits = []

    def time(self):
        return self.now

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return False


def policy(tmp_path, clock, **kw):
    return FangRequestPolicy(tmp_path, clock=clock.time, wait=clock.wait, **kw)


def test_shared_spacing_and_challenge_survives_restart(tmp_path):
    clock = Clock()
    a, b = policy(tmp_path, clock), policy(tmp_path, clock)
    a.perform(lambda: 'first')
    assert b.perform(lambda: 'second') == 'second'
    assert clock.waits == [5]
    with pytest.raises(FangChallenge):
        a.perform(lambda: (_ for _ in ()).throw(FangChallenge('滑块')))
    c = policy(tmp_path, clock)
    called = []
    with pytest.raises(FangCoolingDown):
        c.perform(lambda: called.append(True))
    assert called == []
    assert c.status()['cooldown_until'] == clock.now + 3600
    for duration in (6 * 3600, 24 * 3600):
        clock.now = c.status()['cooldown_until'] + 1
        with pytest.raises(FangChallenge):
            c.perform(lambda: (_ for _ in ()).throw(FangChallenge('滑块')))
        assert c.status()['cooldown_until'] == clock.now + duration
    clock.now += 24 * 3600 + 1
    c.perform(lambda: 'list succeeded')
    assert c.status()['challenge_level'] == 3
    c.mark_complete()
    assert c.status()['challenge_level'] == 0


def test_timeout_retry_is_bounded_and_not_a_challenge(tmp_path):
    clock = Clock()
    p = policy(tmp_path, clock)
    calls = []
    def fetch():
        calls.append(1)
        raise TimeoutError('timeout')
    with pytest.raises(FangTemporarilyUnavailable):
        p.perform(fetch)
    assert len(calls) == 2
    assert max(clock.waits) >= 30
    with pytest.raises(FangTemporarilyUnavailable):
        p.perform(fetch)
    assert len(calls) == 2
    assert p.status()['challenge_level'] == 0


def test_cancel_and_corrupt_state_fail_closed(tmp_path):
    clock = Clock()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(FangRequestCancelled):
        policy(tmp_path, clock, cancel_event=cancel).perform(lambda: 1)
    p = policy(tmp_path, clock)
    p.path.write_text('{bad', encoding='utf-8')
    with pytest.raises(FangCoolingDown):
        p.perform(lambda: 1)
    assert p.status()['cooldown_until'] > clock.now


def test_cache_ttl_source_isolation_and_dynamic_fields(tmp_path):
    clock = Clock()
    cache = FangDetailCache(tmp_path, clock=clock.time)
    row = dict(source_listing_id='3_123_1', source_community_id='123',
               detail_fetched=True, address='滨江区测试路', property_type='住宅', monthly_rent_yuan=100)
    cache.put(row)
    result = cache.get(row)
    assert result['address'] == row['address']
    assert 'monthly_rent_yuan' not in result
    assert cache.get({**row, 'source_community_id': '456'}) is None
    clock.now += 7 * 86400
    assert cache.get(row) is None
    cache.put({**row, 'detail_fetched': False})
    assert cache.get(row) is None


URL = 'https://zu.fang.com/hz/house-xm123/'
DETAIL = 'https://zu.fang.com/hz/chuzu/3_123_1.htm'
HTML = '''房天下 <dl><a href="/hz/chuzu/3_123_1.htm">房源</a>
<p>整租 | 2室1厅 | 80㎡</p><a href="/hz/house-xm123/">测试花园</a><p>6000 元/月</p></dl>'''
DETAIL_HTML = '房天下 费用明细 物业类型 住宅 地 址 滨江区测试路 地图'


def test_two_crawls_only_refresh_dynamic_list_fields(tmp_path):
    cache = FangDetailCache(tmp_path)
    calls = []
    def fetch(url):
        calls.append(url)
        return HTML if url == URL else DETAIL_HTML
    first = list(crawl_runs([URL], fetch=fetch, delay=0, details=True, detail_cache=cache))[0]
    assert first.status == 'complete'
    second = list(crawl_runs([URL], fetch=lambda u: calls.append(u) or HTML.replace('6000', '6500'),
                            delay=0, details=True, detail_cache=cache))[0]
    assert calls == [URL, DETAIL, URL]
    assert second.samples[0]['monthly_rent_yuan'] == 6500
    assert second.samples[0]['detail_verified_at'] == first.samples[0]['detail_verified_at']
    assert second.detail_cache_hits == 1


def test_detail_challenge_stops_all_following_requests():
    calls = []
    def fetch(url):
        calls.append(url)
        if url == URL:
            return HTML
        raise FangChallenge('滑块')
    results = list(crawl_runs([URL, URL.replace('xm123', 'xm456')], fetch=fetch, delay=0, details=True))
    assert calls == [URL, DETAIL]
    assert results[0].status == 'partial_detail'
    assert results[1].deferred is True


def test_other_client_can_cancel_while_waiting_for_shared_lock(tmp_path):
    entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    a = FangRequestPolicy(tmp_path, interval=0)
    b = FangRequestPolicy(tmp_path, interval=0, cancel_event=cancelled)
    errors, calls = [], []
    def held_request():
        entered.set()
        assert release.wait(3)
    first = threading.Thread(target=lambda: a.perform(held_request))
    def second_request():
        try:
            b.perform(lambda: calls.append(1))
        except FangRequestCancelled:
            errors.append('cancelled')
    second = threading.Thread(target=second_request)
    first.start()
    try:
        assert entered.wait(2)
        second.start()
        cancelled.set()
        second.join(2)
        assert errors == ['cancelled'] and calls == []
    finally:
        release.set()
        first.join(3)


def test_expired_and_corrupt_cache_entries_do_not_accumulate(tmp_path):
    clock = Clock()
    cache = FangDetailCache(tmp_path, clock=clock.time)
    row = dict(source_listing_id='3_123_1', source_community_id='123', detail_fetched=True,
               property_type='住宅', address=None)
    cache.put(row)
    clock.now += 7 * 86400
    cache.prune()
    assert list(cache.directory.glob('*.json')) == []
    cache.put(row)
    path = next(cache.directory.glob('*.json'))
    path.write_text('{bad', encoding='utf-8')
    assert cache.get(row) is None
    assert not path.exists()


def test_list_only_crawl_does_not_reset_challenge_level(tmp_path):
    clock = Clock()
    p = policy(tmp_path, clock)
    with pytest.raises(FangChallenge):
        p.perform(lambda: (_ for _ in ()).throw(FangChallenge('滑块')))
    clock.now += 3601
    class Client:
        policy = p
        def fetch(self, url): return HTML
    crawl([URL], fetch=Client().fetch, delay=0, details=False)
    assert p.status()['challenge_level'] == 1
