"""Offline tests for the per-seed, cancellable crawl layer (crawl_runs)."""
import threading
import time

import pytest

from src.services.fang_rentals import CHALLENGE_PAUSE_MESSAGE, CrawlProgress, FangChallenge, RentalCrawlCancelled, crawl_runs

URL = 'https://zu.fang.com/hz/house-xm2010067741/'
NEXT_URL = 'https://zu.fang.com/hz/house-xm2010067741/i32/'
DETAIL_URL = 'https://zu.fang.com/hz/chuzu/3_123_1.htm'
SECOND = 'https://zu.fang.com/hz/house-xm998/'
SECOND_NEXT = 'https://zu.fang.com/hz/house-xm998/i32/'
DETAIL_HTML = '<title>房天下</title>费用明细 物业类型 住宅 地 址 月明路1076号 电话咨询'


def page(rows, next_link=''):
    return '<title>杭州租房 - 房天下</title><div class="houseList">' + rows + '</div>' + next_link


def listing(id='3_123_1', mode='整租', title='三房出租'):
    return f'''<dl><dt><a href="/hz/chuzu/{id}.htm">图片</a></dt><dd>
    <p class="title"><a href="/hz/chuzu/{id}.htm">{title}</a></p>
    <p class="font15">{mode} | 3室2厅 | 89㎡ | 朝南</p>
    <p><a>滨江</a>-<a>长河</a>-<a href="/hz/house-xm2010067741/">风雅钱塘</a></p>
    <div class="moreInfo"><p><b>6,400</b> 元/月</p></div></dd></dl>'''


def next_link(url):
    return f'<a href="{url}">下一页</a>'


def collect(seeds, **kwargs):
    return list(crawl_runs(seeds, **kwargs))


def test_complete_seed_over_two_pages():
    pages = {URL: page(listing(), next_link(NEXT_URL)), NEXT_URL: page(listing('1_456_1'))}
    results = collect([URL], fetch=lambda u: pages[u], delay=0)
    assert len(results) == 1
    result = results[0]
    assert result.status == 'complete'
    assert result.pages_fetched == 2
    assert result.pages_truncated is False
    assert result.detail_success == 0 and result.detail_failed == 0
    assert [row['source_listing_id'] for row in result.samples] == ['3_123_1', '1_456_1']
    assert result.errors == []


def test_truncated_when_pagination_hits_limit():
    pages = {URL: page(listing(), next_link(NEXT_URL)), NEXT_URL: page(listing('1_456_1'))}
    results = collect([URL], fetch=lambda u: pages[u], max_pages=1, delay=0)
    assert results[0].status == 'truncated'
    assert results[0].pages_truncated is True
    assert results[0].pages_fetched == 1
    assert len(results[0].samples) == 1


def test_list_failed_on_first_page_has_no_samples():
    results = collect([URL], fetch=lambda u: '<title>登录</title>', delay=0)
    assert results[0].status == 'list_failed'
    assert results[0].samples == []
    assert results[0].pages_fetched == 0
    assert results[0].errors[0]['stage'] == 'list'


def test_list_failed_on_later_page_keeps_fetched_samples():
    pages = {URL: page(listing(), next_link(NEXT_URL)), NEXT_URL: '<html>验证您的身份</html>'}
    results = collect([URL], fetch=lambda u: pages[u], delay=0)
    assert results[0].status == 'list_failed'
    assert len(results[0].samples) == 1
    assert results[0].pages_fetched == 1


def test_empty_listing_is_empty_ok():
    results = collect([URL], fetch=lambda u: page('', '<p>暂无房源</p>'), delay=0)
    assert results[0].status == 'empty_ok'
    assert results[0].samples == []
    assert results[0].pages_fetched == 1
    assert results[0].errors == []


def test_detail_failure_marks_partial_detail():
    pages = {URL: page(listing()), DETAIL_URL: '<title>登录</title>'}
    results = collect([URL], fetch=lambda u: pages[u], delay=0, details=True)
    assert results[0].status == 'partial_detail'
    assert results[0].detail_failed == 1 and results[0].detail_success == 0
    assert 'detail_fetch_failed' in results[0].samples[0]['quality_flags']
    assert results[0].errors[0]['stage'] == 'detail'


def test_successful_details_keep_complete_status():
    pages = {URL: page(listing()), DETAIL_URL: DETAIL_HTML}
    results = collect([URL], fetch=lambda u: pages[u], delay=0, details=True)
    assert results[0].status == 'complete'
    assert results[0].detail_success == 1 and results[0].detail_failed == 0
    assert results[0].samples[0]['address'] == '月明路1076号'


def test_truncated_wins_over_partial_detail():
    pages = {URL: page(listing(), next_link(NEXT_URL)), NEXT_URL: page(listing('1_456_1')),
             DETAIL_URL: '<title>登录</title>'}
    results = collect([URL], fetch=lambda u: pages[u], max_pages=1, delay=0, details=True)
    assert results[0].status == 'truncated'
    assert results[0].detail_failed == 1


def test_cancel_before_first_request():
    event = threading.Event()
    event.set()
    with pytest.raises(RentalCrawlCancelled) as excinfo:
        collect([URL], fetch=lambda u: page(listing()), delay=0, cancel_event=event)
    assert excinfo.value.completed == []
    assert excinfo.value.partial is not None
    assert excinfo.value.partial.seed == URL
    assert excinfo.value.partial.samples == []


def test_cancel_during_delay_wakes_wait():
    event = threading.Event()
    pages = {URL: page(listing(), next_link(NEXT_URL)), NEXT_URL: page(listing('1_456_1'))}

    def cancel_soon():
        time.sleep(0.1)
        event.set()

    threading.Thread(target=cancel_soon, daemon=True).start()
    started = time.monotonic()
    with pytest.raises(RentalCrawlCancelled) as excinfo:
        collect([URL], fetch=lambda u: pages[u], delay=5, cancel_event=event)
    elapsed = time.monotonic() - started
    assert elapsed < 3, 'cancel_event.wait must be woken by set(), not sleep the full delay'
    assert excinfo.value.completed == []
    assert excinfo.value.partial is not None
    assert len(excinfo.value.partial.samples) == 1


def test_cancel_keeps_completed_seeds():
    event = threading.Event()
    pages = {URL: page(listing()),
             SECOND: page(listing('1_456_1'), next_link(SECOND_NEXT)),
             SECOND_NEXT: page(listing('2_789_1'))}

    def fetch(url):
        if url == SECOND:
            event.set()
        return pages[url]

    with pytest.raises(RentalCrawlCancelled) as excinfo:
        collect([URL, SECOND], fetch=fetch, delay=0, cancel_event=event)
    assert [result.seed for result in excinfo.value.completed] == [URL]
    assert excinfo.value.completed[0].status == 'complete'
    assert excinfo.value.partial is not None
    assert excinfo.value.partial.seed == SECOND
    assert len(excinfo.value.partial.samples) == 1


def test_no_cancel_event_crawls_normally():
    pages = {URL: page(listing())}
    results = collect([URL], fetch=lambda u: pages[u], delay=0)
    assert results[0].status == 'complete'


def test_cross_seed_dedup_counts_duplicates():
    pages = {URL: page(listing('3_123_1')), SECOND: page(listing('3_123_1'))}
    results = collect([URL, SECOND], fetch=lambda u: pages[u], delay=0)
    assert results[0].status == 'complete'
    assert len(results[0].samples) == 1
    assert results[1].status == 'complete'
    assert results[1].duplicate_ids == 1
    assert results[1].samples == []


def test_progress_tracks_crawl():
    progress = CrawlProgress(total_seeds=2)
    pages = {URL: page(listing()), DETAIL_URL: DETAIL_HTML,
             SECOND: page('', '<p>暂无房源</p>')}
    seen = []

    def fetch(url):
        seen.append(progress.snapshot())
        return pages[url]

    collect([URL, SECOND], fetch=fetch, delay=0, details=True, progress=progress)
    assert progress.total_seeds == 2
    assert progress.processed_seeds == 2
    assert progress.current_seed is None
    assert progress.pages_fetched == 2
    assert progress.details_fetched == 1
    assert seen[0] == {'total_seeds': 2, 'processed_seeds': 0, 'current_seed': URL,
                       'pages_fetched': 0, 'details_fetched': 0}


def test_invalid_limits_rejected():
    with pytest.raises(ValueError):
        collect([URL], fetch=lambda u: page(listing()), max_pages=0, delay=0)
    with pytest.raises(ValueError):
        collect([URL], fetch=lambda u: page(listing()), delay=-1)


def test_challenge_streak_pauses_remaining_seeds():
    calls = []

    def fetch(url):
        calls.append(url)
        raise FangChallenge('房天下要求滑块验证（IP 被风控），请稍后重试')

    seeds = [URL, SECOND, 'https://zu.fang.com/hz/house-xm997/', 'https://zu.fang.com/hz/house-xm996/']
    results = collect(seeds, fetch=fetch, delay=0)
    assert len(results) == 4
    assert [r.status for r in results] == ['list_failed'] * 4
    assert results[0].errors[0]['error'].startswith('房天下要求滑块验证')
    assert results[2].deferred and results[3].deferred
    assert len(calls) == 1  # first challenge pauses every subsequent seed


def test_first_challenge_pauses_next_seed():
    def fetch(url):
        if url == URL:
            raise FangChallenge('房天下要求滑块验证（IP 被风控），请稍后重试')
        return page(listing())

    results = collect([URL, SECOND], fetch=fetch, delay=0)
    assert results[0].status == 'list_failed'
    assert results[1].status == 'list_failed'
    assert results[1].deferred
