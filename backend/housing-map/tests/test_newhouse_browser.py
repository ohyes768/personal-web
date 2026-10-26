"""Browser evidence stays independent from admission and ESF identity."""
from types import SimpleNamespace

import pytest

from src.services.tmsf_property_type import fetch_project_facts_by_id

PID = '2946115152'
NAME = '春来晴翠园'
ALIAS = '绿城英冠春来晴翠'
URL = f'https://www.tmsf.com/newhouse/property_33_{PID}_infoUpgrade.htm'
CERT = f'https://www.tmsf.com/newhouse/presell_33_{PID}_3333500499.htm'
ADDRESS = '东至规划道路，南至零磁谷街绿化，西至浦沿路绿化，北至回龙庵街。'
HOME = f'''<div class="house_float_name_title">{NAME}</div>
<a id="districtname">滨江楼盘</a><span class="house_information_price_residence">住宅</span>
<span class="house_float_name_tips_greenlight">在售</span>
<div>楼盘地址</div><div>东至规划道路，南至零磁谷街绿..</div>
<a href="/newhouse/presell_33_{PID}_3333500499.htm">202600601</a>'''
CERTIFICATE = f'''<td>楼盘名称</td><td id="propertynamerr">{ALIAS}</td>
<td>楼盘坐落</td><td id="locatedrr">{ADDRESS}</td>
<td>售楼部地址</td><td id="selladdressrr">另一个售楼地址</td>
<td>预售证号</td><td id="persellnorr">202600601</td>'''


def upstream(home=HOME, certificate=CERTIFICATE):
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        if url == URL:
            return home
        if isinstance(certificate, Exception):
            raise certificate
        assert url == CERT
        return certificate
    return SimpleNamespace(fetch_text=lambda *_: '<html>JS verification</html>',
                           fetch_project_text=fetch), calls


def facts(client):
    return fetch_project_facts_by_id(client, siteid='33', propertyid=PID,
                                    names=[NAME, ALIAS], district='滨江')


def test_browser_fetches_complete_location_from_same_project_certificate():
    client, calls = upstream()
    value = facts(client)
    assert value['property_type'] == '住宅'
    assert value['address'] == ADDRESS
    assert value['address_evidence_url'] == CERT
    assert value['address_certificate_number'] == '202600601'
    assert calls == [URL, CERT]


@pytest.mark.parametrize('certificate', [CERTIFICATE.replace(ALIAS, ALIAS + '二期'),
    CERTIFICATE.replace('202600601', '202600600'), CERTIFICATE.replace(ADDRESS, '暂无'),
    CERTIFICATE.replace(ADDRESS, '浦沿路..')])
def test_wrong_or_incomplete_certificate_keeps_verified_use_only(certificate):
    client, calls = upstream(certificate=certificate)
    value = facts(client)
    assert value['property_type'] == '住宅' and value['market_state'] == 'new_house'
    assert not value['address'] and value['address_error']
    assert 'address_evidence_url' not in value
    assert len(calls) == 2


def test_foreign_project_certificate_is_never_requested():
    client, calls = upstream(home=HOME.replace(f'presell_33_{PID}_', 'presell_33_999_'))
    value = facts(client)
    assert not value['address'] and value['address_error']
    assert calls == [URL]


def test_address_timeout_does_not_lose_verified_use():
    client, _ = upstream(certificate=TimeoutError())
    value = facts(client)
    assert value['property_type'] == '住宅' and value['address_error']


def test_cancelled_address_request_is_not_published_as_partial_success():
    client, _ = upstream(certificate=InterruptedError())
    with pytest.raises(InterruptedError):
        facts(client)


def test_address_retry_reuses_recent_detail_but_rechecks_certificate():
    client, calls = upstream(certificate=TimeoutError())
    first = facts(client)
    assert not first['address']
    client, calls = upstream()
    value = fetch_project_facts_by_id(client, siteid='33', propertyid=PID,
        names=[NAME, ALIAS], district='滨江', previous=first)
    assert value['address'] == ADDRESS and calls == [CERT]


def test_expired_or_other_identity_cache_cannot_skip_detail():
    client, _ = upstream(certificate=TimeoutError())
    first = facts(client)
    first['newhouse_detail_cache']['checked_at'] = '2020-01-01T00:00:00+00:00'
    client, calls = upstream()
    value = fetch_project_facts_by_id(client, siteid='33', propertyid=PID,
        names=[NAME, ALIAS], district='滨江', previous=first)
    assert value['address'] == ADDRESS and calls == [URL, CERT]


def test_missing_home_address_can_still_use_verified_certificate():
    client, _ = upstream(home=HOME.replace('东至规划道路，南至零磁谷街绿..', ''))
    assert facts(client)['address'] == ADDRESS


def test_enrichment_reports_address_failure_and_preserves_old_verified_address(tmp_path):
    from src.services.community_registry import CommunityRegistry
    from src.services.community_enrichment import enrich_source
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    source = store.ingest(dict(source='tmsf', source_kind='project', source_id=PID, name=NAME,
        aliases=[ALIAS], district='滨江', project_siteid='33', project_id=PID,
        address='已核验历史地址', address_checked_at='2026-10-01T00:00:00+00:00'))
    client, _ = upstream(certificate=TimeoutError())
    result = enrich_source(store, tmp_path, source['id'], tmsf_client=client, include_position=False)
    assert result['errors'] and '地址' in result['errors'][0]
    saved = store.sources()[0]
    assert saved['address'] == '已核验历史地址' and saved['property_type'] == '住宅'


def test_observed_sale_status_takes_priority_over_index_fallback():
    from src.services.tmsf_property_type import _project_detail
    client, _ = upstream(home=HOME.replace('在售</span>', '售完</span>'))
    result = _project_detail(client, URL, [NAME, ALIAS], '滨江', 15, fallback_status='在售')
    assert result['project_sale_status'] == '售完' and result['market_state'] == 'second_hand'
