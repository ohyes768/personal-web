"""Discovery adapter: identity is proven by the homepage, never by a search."""
import json

import pytest

from src.services import xingfuli_discovery as disc
from src.services import xingfuli_rentals as xfl

TOTAL_ID = '6581009489657331972'
SEED = '7406856173871235098'
PHASE_ID = '6598511715770433795'
NOISE_ID = '6581010025748103431'


def homepage_html(neighborhood_id=TOTAL_ID, name='白金海岸', address='香溢路88号',
                  longitude='120.188369', latitude='30.203001', seeds=(SEED,), total=31):
    payload = {'data': {'loadersData': {f'"@neighborDetail_{neighborhood_id}"': {'data': {
        'neighborhood_info': {'id': neighborhood_id, 'name': name, 'address': address,
                               'gaode_lng': longitude, 'gaode_lat': latitude},
        'rentInNeighbor': {'total': total, 'has_more': True,
                           'items': [{'id': seed, 'title': '整租 白金海岸'} for seed in seeds]},
    }}}}}
    return '<html><script>window._SSR_DATA = ' + json.dumps(payload, ensure_ascii=False) + ';</script></html>'


def search_payload(items, status=0):
    return json.dumps({'status': status, 'message': 'success', 'data': {'total': len(items), 'items': items}})


def listing_html(neighborhood_id=TOTAL_ID, listing_id=SEED, rows=2):
    payload = {'query': {'city': 'hz', 'id': listing_id},
               'data': {'status': 1, 'info': {'card_info': {'neighborhood': {
                   'open_url': f'https://m.xflapp.com/xiaoqu/hz-{neighborhood_id}.html?neighborhood_id={neighborhood_id}'}}}}}
    return '<html><script name="pia-ssr-data" type="application/json">' + json.dumps(payload) + '</script></html>'


def list_html(neighborhood_id=TOTAL_ID, listing_id=SEED, owners=None):
    owners = owners or [neighborhood_id] * 2
    payload = {'query': {'city': 'hz', 'id': listing_id},
               'data': {'status': 1, '_hasMore': False,
                        '_list': [{'id': str(i), 'neighborhood_id': owner} for i, owner in enumerate(owners)]}}
    return '<html><script name="pia-ssr-data" type="application/json">' + json.dumps(payload) + '</script></html>'


def discovery(tmp_path, pages):
    def fetch(url):
        for pattern, body in pages.items():
            if pattern in url:
                return body
        raise AssertionError(f'未预期的请求: {url}')
    return disc.XingfuliDiscovery(directory=tmp_path, fetcher=fetch, delay=0), fetch


# --- URL whitelist -------------------------------------------------------

def test_discovery_url_allows_search_and_homepage():
    disc.validate_discovery_url('https://m.xflapp.com/f100/api/search?city_id=1853&house_type=2&channel_id=94349530167&full_text=x&count=20&offset=0&page_type=house_list')
    disc.validate_discovery_url(f'https://m.xflapp.com/xiaoqu/hz-{TOTAL_ID}.html')


@pytest.mark.parametrize('url', [
    'http://m.xflapp.com/xiaoqu/hz-1.html',
    'https://evil.com/xiaoqu/hz-1.html',
    'https://m.xflapp.com/xiaoqu/hz-1.html?x=1',
    'https://m.xflapp.com/f100/api/search?city_id=1853&callback=alert',
    'https://m.xflapp.com/f100/api/search_api/rent?house_id=1',
    'https://m.xflapp.com/xiaoqu/hz-abc.html',
])
def test_discovery_url_rejects_everything_else(url):
    with pytest.raises(ValueError):
        disc.validate_discovery_url(url)


# --- homepage parsing ----------------------------------------------------

def test_homepage_yields_identity_and_entry():
    info = disc.parse_homepage(homepage_html(), TOTAL_ID)
    assert info['name'] == '白金海岸'
    assert info['address'] == '香溢路88号'
    assert info['longitude'] == pytest.approx(120.188369)
    assert info['latitude'] == pytest.approx(30.203001)
    assert info['coordinate_system'] == 'gcj02'
    assert info['seeds'] == [SEED]
    assert info['rent_total'] == 31


def test_homepage_without_rent_module_has_no_entry():
    payload = {'data': {'loadersData': {f'"@neighborDetail_{TOTAL_ID}"': {'data': {
        'neighborhood_info': {'id': TOTAL_ID, 'name': '白金海岸', 'address': '香溢路88号',
                               'gaode_lng': '120.188369', 'gaode_lat': '30.203001'}}}}}}
    html = '<html><script>window._SSR_DATA = ' + json.dumps(payload) + ';</script></html>'
    info = disc.parse_homepage(html, TOTAL_ID)
    assert info['seeds'] == []
    assert info['rent_total'] is None


def test_homepage_identity_must_match_request():
    with pytest.raises(ValueError):
        disc.parse_homepage(homepage_html(), PHASE_ID)


def test_homepage_challenge_page_is_rejected():
    with pytest.raises(ValueError):
        disc.parse_homepage('<html>请输入验证码</html>', TOTAL_ID)


def test_homepage_without_payload_is_rejected():
    with pytest.raises(ValueError):
        disc.parse_homepage('<html><body>hello</body></html>', TOTAL_ID)


# --- search item shapes --------------------------------------------------

def test_search_groups_reads_each_channel_shape():
    second_hand = [{'neighborhood_info': {'id': TOTAL_ID},
                    'core_info': [{'attr': '小区名', 'value': '白金海岸'}]}]
    rent = [{'neighborhood_id': '6584028761644073220', 'id': '7687465012021936163',
             'title': '整租·万科璞悦湾 5室4厅'}]
    neighborhood = [{'id': PHASE_ID, 'neighborhood_info': {'id': PHASE_ID, 'name': '白金海岸(北区)'}}]
    assert disc.search_groups(second_hand, 'second_hand') == {TOTAL_ID: {'name': '白金海岸', 'seeds': []}}
    assert disc.search_groups(rent, 'rent') == {
        '6584028761644073220': {'name': '万科璞悦湾', 'seeds': ['7687465012021936163']}}
    assert disc.search_groups(neighborhood, 'neighborhood') == {PHASE_ID: {'name': '白金海岸(北区)', 'seeds': []}}


def test_search_groups_ignores_items_without_identity():
    assert disc.search_groups([{'neighborhood_id': '', 'title': '整租· 2室1厅'}]) == {}
    assert disc.search_groups([{'title': '整租· 2室1厅'}]) == {}
    assert disc.search_groups([{'neighborhood_id': '123', 'title': '整租·未知小区 2室1厅'}], 'rent') == {
        '123': {'name': '未知小区', 'seeds': []}}


# --- phase / district conflicts -----------------------------------------

def test_phase_marker_is_read_from_the_platform_name():
    assert disc.phase_of('白金海岸(南区)') == '南区'
    assert disc.phase_of('白金海岸（北区）') == '北区'
    assert disc.phase_of('白金海岸') == ''


def test_address_district_reads_the_named_district():
    assert disc.address_district('萧山区北干街道金城路') == '萧山区'
    assert disc.address_district('香溢路88号') == ''


# --- discovery client ----------------------------------------------------

def test_search_returns_named_neighborhoods(tmp_path):
    body = search_payload([{'neighborhood_info': {'id': TOTAL_ID},
                             'core_info': [{'attr': '小区名', 'value': '白金海岸'}]}])
    client, _ = discovery(tmp_path, {'/f100/api/search': body})
    assert client.search('白金海岸', 'second_hand') == {TOTAL_ID: {'name': '白金海岸', 'seeds': []}}


def test_search_rejects_a_failed_status(tmp_path):
    client, _ = discovery(tmp_path, {'/f100/api/search': search_payload([], status=1)})
    with pytest.raises(ValueError):
        client.search('白金海岸', 'second_hand')


def test_community_info_reads_the_api_without_rental_entry(tmp_path):
    body = json.dumps({'status': 0, 'data': {'neighborhood_info': {
        'id': TOTAL_ID, 'name': '白金海岸', 'address': '香溢路88号',
        'city_id': 1853, 'district_name': '滨江', 'gaode_lng': '120.188369', 'gaode_lat': '30.203001'}}})
    client, _ = discovery(tmp_path, {'/f100/api/neighborhood/info': body})
    info = client.community_info(TOTAL_ID)
    assert info['name'] == '白金海岸'
    assert 'seeds' not in info and 'rent_total' not in info
    assert client.request_count == 1


def test_listing_owner_comes_from_the_detail_page(tmp_path):
    client, _ = discovery(tmp_path, {f'/zufang/hz-{SEED}.html': listing_html()})
    assert client.listing_owner(SEED) == TOTAL_ID


def test_list_must_belong_to_the_community(tmp_path):
    client, _ = discovery(tmp_path, {f'/zufang/neighbor-house-list/hz-{SEED}.html':
                                      list_html(owners=[TOTAL_ID, NOISE_ID])})
    assert client.listing_owner_from_list(SEED, TOTAL_ID) is False


def test_list_belonging_to_the_community_is_accepted(tmp_path):
    client, _ = discovery(tmp_path, {f'/zufang/neighbor-house-list/hz-{SEED}.html': list_html()})
    assert client.listing_owner_from_list(SEED, TOTAL_ID) is True


# --- the collector keeps its own stricter whitelist ----------------------

def test_collector_still_rejects_discovery_paths():
    with pytest.raises(ValueError):
        xfl.validate_url(f'https://m.xflapp.com/xiaoqu/hz-{TOTAL_ID}.html')
    with pytest.raises(ValueError):
        xfl.validate_url('https://m.xflapp.com/f100/api/search?city_id=1853')
