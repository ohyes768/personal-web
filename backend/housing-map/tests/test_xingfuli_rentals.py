"""Offline contract tests for the public Hangzhou Xingfuli rental pages."""
import json
import threading

import pytest

from src.services import xingfuli_rentals as xfl

SID = '6581030816598458638'
SEED = '7502229388495274018'
LID = '7660466810168328198'


def row(lid=LID, sid=SID, mode=1, title='整租·风雅钱塘 3室1厅'):
    return dict(id=lid, neighborhood_id=sid, rental_type=mode, rent_price='6000',
                rent_price_unit='元/月', title=title, sub_title='130.76㎡ | 南 | 滨江 滨江区政府')


def html(data, query=None):
    return '<script name="pia-ssr-data" type="application/json">' + json.dumps(
        dict(query=query or dict(city='hz', id=SEED), data=data), ensure_ascii=False) + '</script>'


def listing(rows=None, more=False, offset=20):
    return html(dict(status=1, _list=[row()] if rows is None else rows, _hasMore=more,
                     _updateParams=dict(offset=offset, search_id='opaque-cursor', refresh_type=2)))


def detail(lid=LID, sid=SID):
    return html(dict(status=1, info=dict(card_info=dict(
        core_data=dict(main_info=dict(name='整租·风雅钱塘', price='6000', price_unit='元/月'),
                       core_info=[dict(attr='面积', value='130.76㎡'), dict(attr='户型', value='3室1厅'),
                                  dict(attr='楼层', value='中 | 共27层')]),
        neighborhood=dict(open_url=f'sslocal://neighborhood_detail?neighborhood_id={sid}')))),
        query=dict(city='hz', id=lid))


def client(tmp_path, pages):
    def fetch(url):
        if '/search_api/rent?' in url:
            return pages['next']
        return pages[url]
    return xfl.XingfuliClient(directory=tmp_path, fetcher=fetch, delay=0)


def crawl(c, **kwargs):
    return c.crawl(SID, SEED, community_name='风雅钱塘', property_type='住宅', **kwargs)


def test_complete_pagination_and_actual_detail_verification(tmp_path):
    other = '7660466810168328199'
    c = client(tmp_path, {xfl.list_url(SEED): listing(more=True),
        'next': json.dumps(dict(status=0, data=dict(items=[row(other, mode=2, title='合租·风雅钱塘 3室1厅')],
                                 offset=21, search_id='next', has_more=False))),
        xfl.detail_url(LID): detail()})
    result = crawl(c)
    assert result.status == 'complete' and result.pages_fetched == 2
    assert len(result.samples) == 2 and result.detail_success == 1
    whole, shared = result.samples
    assert whole['source_listing_id'] == LID and whole['source_community_id'] == SID
    assert whole['monthly_rent_yuan'] == 6000 and whole['area_m2'] == 130.76
    assert whole['detail_fetched'] and whole['floor'] == '中 | 共27层'
    assert whole['published_at'] is None and whole['price_kind'] == 'listing_rent'
    assert shared['rental_mode'] == 'shared' and 'shared_rental' in shared['quality_flags']


@pytest.mark.parametrize('body', [listing([row(sid='999')]), '<title>验证</title>',
    html(dict(status=1, _list=[], _hasMore=False), query=dict(city='bj', id=SEED))])
def test_wrong_community_challenge_and_city_are_failures(tmp_path, body):
    result = crawl(client(tmp_path, {xfl.list_url(SEED): body}))
    assert result.status == 'list_failed' and result.errors


def test_partial_details_never_count_as_complete(tmp_path):
    result = crawl(client(tmp_path, {xfl.list_url(SEED): listing(),
                                   xfl.detail_url(LID): detail(sid='wrong')}))
    assert result.status == 'partial_detail'
    assert result.samples[0]['detail_fetched'] is False


def test_page_limit_and_stalled_cursor_are_not_complete(tmp_path):
    c = client(tmp_path, {xfl.list_url(SEED): listing(more=True)})
    assert crawl(c, max_pages=1, details=False).status == 'truncated'
    c = client(tmp_path / 'again', {xfl.list_url(SEED): listing(more=True), 'next': json.dumps(
        dict(status=0, data=dict(items=[row()], offset=20, search_id='x', has_more=True)))})
    assert crawl(c, details=False).status == 'list_failed'


def test_empty_complete_and_cancel_before_fetch(tmp_path):
    c = client(tmp_path, {xfl.list_url(SEED): listing([]), xfl.detail_url(SEED): detail(lid=SEED)})
    assert crawl(c).status == 'empty_ok'
    event = threading.Event(); event.set()
    with pytest.raises(xfl.RentalCrawlCancelled):
        crawl(c, cancel_event=event)


def test_empty_list_without_membership_proof_is_not_empty_success(tmp_path):
    c = client(tmp_path, {xfl.list_url(SEED): listing([]), xfl.detail_url(SEED): '<title>已下架</title>'})
    assert crawl(c).status == 'list_failed'


def test_duplicate_final_page_and_api_error_are_not_complete(tmp_path):
    for response in [dict(status=0, data=dict(items=[row()], offset=20, search_id='x', has_more=False)),
                     dict(status=1001, message='params error')]:
        c = client(tmp_path, {xfl.list_url(SEED): listing(more=True), 'next': json.dumps(response)})
        assert crawl(c, details=False).status == 'list_failed'


def test_cancellation_after_http_response_discards_result(tmp_path):
    event = threading.Event()
    def fetch(url):
        event.set()
        return listing()
    c = xfl.XingfuliClient(directory=tmp_path, fetcher=fetch, delay=0)
    with pytest.raises(xfl.RentalCrawlCancelled):
        crawl(c, cancel_event=event)


def test_challenge_cools_down_without_repeated_requests(tmp_path):
    requests = []
    def fetch(url):
        requests.append(url)
        return '<title>captcha</title>'
    c = xfl.XingfuliClient(directory=tmp_path, fetcher=fetch, delay=0)
    assert crawl(c).status == 'list_failed'
    second = crawl(c)
    assert second.deferred and c.cooldown_until and len(requests) == 1


@pytest.mark.parametrize('url', ['http://m.xflapp.com/zufang/hz-123.html',
    'https://m.xflapp.com.evil/zufang/hz-123.html', 'https://u:p@m.xflapp.com/zufang/hz-123.html',
    'https://m.xflapp.com/zufang/bj-123.html', 'https://m.xflapp.com:444/zufang/hz-123.html'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        xfl.validate_url(url)
