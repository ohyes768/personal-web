"""List API sampling, identity checks, pagination and shared request policy."""
import json
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

from src.services import xingfuli_rentals as xfl
from src.services.rental_reference.statistics import select_valid
from src.services.xingfuli_transport import XingfuliTransport

SID = '6581030816598458638'
SEED = '7502229388495274018'
LID = '7660466810168328198'


def row(lid=LID, sid=SID, mode=1, title='整租·风雅钱塘 3室1厅', rent='6000'):
    return dict(id=lid, neighborhood_id=sid, rental_type=mode, rent_price=rent,
                rent_price_unit='元/月', title=title, sub_title='130.76㎡ | 南 | 滨江 滨江区政府')


def html(data, query=None):
    return '<script name="pia-ssr-data" type="application/json">' + json.dumps(
        dict(query=query or dict(city='hz', id=SEED), data=data), ensure_ascii=False) + '</script>'


def detail(lid=LID, sid=SID):
    return html(dict(status=1, info=dict(card_info=dict(
        core_data=dict(main_info=dict(name='整租·风雅钱塘', price='6000', price_unit='元/月'),
                       core_info=[dict(attr='面积', value='130.76㎡'), dict(attr='户型', value='3室1厅'),
                                  dict(attr='楼层', value='中 | 共27层')]),
        neighborhood=dict(open_url=f'sslocal://neighborhood_detail?neighborhood_id={sid}')))),
        query=dict(city='hz', id=lid))


def page(items, more=False, offset=20, search='cursor'):
    return dict(status=0, data=dict(items=items, has_more=more, offset=offset, search_id=search))


def client(tmp_path, pages):
    calls = []
    def fetch(url):
        assert urlsplit(url).path == '/f100/api/search_api/rent', url
        calls.append(parse_qs(urlsplit(url).query))
        response = pages[len(calls) - 1]
        return response if isinstance(response, str) else json.dumps(response)
    return xfl.XingfuliClient(directory=tmp_path, fetcher=fetch, delay=0), calls


def crawl(c, **kwargs):
    return c.crawl(SID, SEED, community_name='风雅钱塘', property_type='住宅', **kwargs)


def rows(start, count):
    return [row(lid=str(900000 + i), rent=str(6000 + i)) for i in range(start, start + count)]


def test_list_api_first_page_stops_at_ten_statistically_valid_samples(tmp_path):
    c, calls = client(tmp_path, [page(rows(0, 20), more=True)])
    result = crawl(c)
    assert result.status == 'complete' and not result.pages_truncated
    valid, _ = select_valid(result.samples)
    assert len(valid) == 10
    assert result.detail_success == result.detail_failed == 0
    assert all(not s['detail_fetched'] for s in result.samples)
    assert valid[0]['verification_method'] == 'xingfuli_list_api_v1'
    assert valid[0]['property_type_origin'] == 'community_directory'
    assert calls[0]['offset'] == ['0'] and calls[0]['house_id'] == [SEED]
    assert 'search_id' not in calls[0] and len(calls) == 1
    assert len(result.samples) == 20  # excluded rows remain auditable


def test_invalid_and_duplicate_rows_do_not_consume_quota(tmp_path):
    invalid = [row(lid='1', mode=2), row(lid='2', title='整租·风雅钱塘 独立厨卫'),
               row(lid='3', rent='0'), row(lid='4', title='整租·风雅钱塘 户型未知')]
    duplicate = row(lid='5', rent='6000')  # same facts as row 900000
    c, calls = client(tmp_path, [page(invalid + rows(0, 4) + [duplicate], True),
                                page(rows(3, 10), False, offset=40)])
    result = crawl(c)
    assert result.status == 'complete'
    valid, audit = select_valid(result.samples)
    assert len(valid) == 10 and result.duplicate_ids == 1
    assert len(audit['suspect_duplicates']) == 1
    assert len(calls) == 2 and calls[1]['offset'] == ['20']
    assert calls[1]['search_id'] == ['cursor']


def test_small_community_saves_actual_samples(tmp_path):
    c, calls = client(tmp_path, [page(rows(0, 3))])
    result = crawl(c)
    assert result.status == 'complete' and len(select_valid(result.samples)[0]) == 3
    assert len(calls) == 1 and result.detail_success == result.detail_failed == 0


@pytest.mark.parametrize('response', [page([row(sid='wrong')]), page([dict(row(), rent_price_unit='元/天')]),
    '<title>验证</title>', dict(status=1001, message='params error'), page([]),
    dict(status=0, data=dict(items=[], has_more='false'))])
def test_unverified_empty_wrong_membership_or_invalid_response_fails(tmp_path, response):
    c, _ = client(tmp_path, [response])
    result = crawl(c)
    assert result.status == 'list_failed' and result.errors


def test_page_limit_stalled_cursor_and_duplicate_final_page(tmp_path):
    c, _ = client(tmp_path, [page(rows(0, 2), True)])
    assert crawl(c, max_pages=1).status == 'truncated'
    c, _ = client(tmp_path / 'cursor', [page(rows(0, 2), True, offset=0)])
    assert crawl(c).status == 'list_failed'
    c, _ = client(tmp_path / 'duplicate', [page(rows(0, 2), True), page(rows(0, 2))])
    assert crawl(c).status == 'list_failed'


def test_even_rows_after_quota_must_belong_to_expected_community(tmp_path):
    c, _ = client(tmp_path, [page(rows(0, 10) + [row(sid='wrong')])])
    assert crawl(c).status == 'list_failed'


def test_cancel_before_and_after_http_response(tmp_path):
    event = threading.Event()
    c, calls = client(tmp_path, [page(rows(0, 2))])
    event.set()
    with pytest.raises(xfl.RentalCrawlCancelled):
        crawl(c, cancel_event=event)
    assert calls == []
    event.clear()
    def fetch(url):
        event.set()
        return json.dumps(page(rows(0, 2)))
    c = xfl.XingfuliClient(directory=tmp_path, fetcher=fetch, delay=0)
    with pytest.raises(xfl.RentalCrawlCancelled):
        crawl(c, cancel_event=event)


def test_challenge_cools_down_without_repeated_requests(tmp_path):
    c, calls = client(tmp_path, ['<title>captcha</title>'])
    assert crawl(c).status == 'list_failed'
    assert crawl(c).deferred and c.cooldown_until and len(calls) == 1


@pytest.mark.parametrize('url', ['http://m.xflapp.com/zufang/hz-123.html',
    'https://m.xflapp.com.evil/zufang/hz-123.html', 'https://u:p@m.xflapp.com/zufang/hz-123.html',
    'https://m.xflapp.com/zufang/bj-123.html', 'https://m.xflapp.com:444/zufang/hz-123.html'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        xfl.validate_url(url)


def test_transport_three_second_minimum_and_explicit_slower_delay(tmp_path):
    assert XingfuliTransport(directory=tmp_path).delay == 3
    assert XingfuliTransport(directory=tmp_path, delay=0).delay == 3
    assert XingfuliTransport(directory=tmp_path, delay=8).delay == 8
    assert XingfuliTransport(directory=tmp_path, fetcher=lambda _: '', delay=0).delay == 0


def test_all_xingfuli_entry_points_default_to_three_seconds(tmp_path):
    from src.services.xingfuli_discovery import XingfuliDiscovery
    from src.services.rental_reference.probe import ProbeService
    from src.services.rental_reference.matching import SourceMatchingService
    from src.services.rental_reference.refresh import RentalRefreshService
    from tests.test_rental_probe import setup
    reg = setup(tmp_path)
    assert xfl.XingfuliClient(directory=tmp_path).delay == 3
    assert XingfuliDiscovery(directory=tmp_path).delay == 3
    assert ProbeService(reg, directory=tmp_path).delay == 3
    assert SourceMatchingService(reg, directory=tmp_path)._probe.delay == 3
    mixed = RentalRefreshService(tmp_path, tmp_path / 'mapping.json')
    assert mixed._delay == 5 and mixed._xingfuli_delay == 3
    assert RentalRefreshService(tmp_path, tmp_path / 'mapping.json', xingfuli_only=True)._xingfuli_delay == 3


def test_source_matching_html_membership_parser_remains_available():
    assert xfl.listing_neighborhood(detail(), LID) == SID
    with pytest.raises(ValueError, match='城市或房源 ID'):
        xfl.listing_neighborhood(detail(), SEED)


def test_list_sampling_statistics_keeps_minimum_group_threshold(tmp_path):
    from src.services.rental_reference.statistics import group_stats
    c, _ = client(tmp_path, [page(rows(0, 2))])
    valid, _ = select_valid(crawl(c).samples)
    stats = group_stats(valid, bedrooms=None, band=None)
    assert stats['sample_count'] == 2
    assert stats['rent_reference'] is None


def test_three_second_interval_uses_persisted_shared_request_state(tmp_path, monkeypatch):
    from src.services import xingfuli_transport
    (tmp_path / 'xingfuli_request_state.json').write_text(json.dumps(
        dict(last_request_at=100, cooldown_until=0)))
    monkeypatch.setattr(xingfuli_transport.time, 'time', lambda: 101)
    first = XingfuliTransport(directory=tmp_path, fetcher=lambda _: '{}', delay=3)
    waits = []
    monkeypatch.setattr(first, '_check_cancel', lambda seconds=0: waits.append(seconds))
    first.fetch('https://m.xflapp.com/f100/api/search_api/rent')
    assert 2 in waits  # 100 + 3 - 101
    second = XingfuliTransport(directory=tmp_path, fetcher=lambda _: '{}', delay=3)
    waits.clear()
    monkeypatch.setattr(second, '_check_cancel', lambda seconds=0: waits.append(seconds))
    second.fetch('https://m.xflapp.com/f100/api/search_api/rent')
    assert 3 in waits  # another client observes the same persisted slot


@pytest.mark.parametrize('subtitle', ['-20㎡ | 南', '0㎡ | 南', '面积未知'])
def test_invalid_area_does_not_enter_list_statistics(tmp_path, subtitle):
    c, _ = client(tmp_path, [page([dict(row(), sub_title=subtitle)])])
    result = crawl(c)
    assert result.status == 'complete'
    assert select_valid(result.samples)[0] == []
