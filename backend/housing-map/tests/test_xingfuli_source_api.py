"""Community APIs separate identity evidence from rental-entry authority."""
import json
import threading
import time
from urllib.parse import parse_qs, urlsplit

import pytest

from src.services.rental_reference.discovery_checkpoint import DiscoveryCheckpoint, PREFIX, VERSION
from src.services.rental_reference.probe import ProbeService
from src.services.xingfuli_discovery import (
    XingfuliDiscovery, parse_community_info, parse_rental_entry, validate_discovery_url)
from tests.test_rental_probe import setup, run, TOTAL_ID, SEED
from tests.test_xingfuli_discovery import listing_html, list_html

OTHER = '6581009489657331973'


def info_body(nid=TOTAL_ID, **changes):
    info = dict(id=nid, name='测试花园', address='测试路1号', city_id=1853,
                district_name='滨江', gaode_lng='120.188369', gaode_lat='30.203001')
    info.update(changes)
    return json.dumps(dict(status=0, data=dict(neighborhood_info=info)))


def entry_body(items=None, total=1, more=False):
    return json.dumps(dict(status=0, data=dict(
        items=[dict(id=SEED)] if items is None else items, total=total, has_more=more)))


class APIResponses:
    def __init__(self, *, ambiguous=False):
        self.calls = []
        self.infos = {TOTAL_ID: info_body()}
        if ambiguous:
            self.infos[OTHER] = info_body(OTHER)
        self.entries = {TOTAL_ID: entry_body()}
        self.rental_rows = [dict(id=SEED, neighborhood_id=TOTAL_ID)]

    def __call__(self, url):
        self.calls.append(url)
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if parts.path == '/f100/api/search':
            items = [dict(neighborhood_info=dict(id=nid, name='测试花园')) for nid in self.infos]
            return json.dumps(dict(status=0, data=dict(items=items, total=len(items))))
        if parts.path == '/f100/api/neighborhood/info':
            return self.infos[query['neighborhood_id'][0]]
        if parts.path == '/f100/api/same_neighborhood_rent':
            assert query['city_id'] == ['1853'] and query['offset'] == ['0'] and query['count'] == ['10']
            return self.entries[query['neighborhood_id'][0]]
        if parts.path == '/f100/api/search_api/rent':
            return json.dumps(dict(status=0, data=dict(items=self.rental_rows, has_more=False)))
        if parts.path == f'/zufang/hz-{SEED}.html':
            return listing_html()
        if parts.path == f'/zufang/neighbor-house-list/hz-{SEED}.html':
            return list_html()
        raise AssertionError('Unexpected request: ' + url)

    def paths(self):
        return [urlsplit(u).path for u in self.calls]


def probe(registry, responses, tmp_path, **kwargs):
    return ProbeService(registry, directory=tmp_path / 'rentals', delay=0,
                        discovery_factory=lambda **options: XingfuliDiscovery(
                            fetcher=responses, **options), **kwargs)


def test_cold_matching_uses_four_api_requests_and_no_listing_html(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'bound_pending_collection'
    assert state['diagnostics']['requests'] == 4
    assert responses.paths() == [
        '/f100/api/search', '/f100/api/neighborhood/info', '/f100/api/same_neighborhood_rent',
        '/f100/api/search_api/rent']


def test_name_only_identity_binds_through_live_api_membership_check(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.infos[TOTAL_ID] = info_body(address='西兴路1190号', gaode_lng=None, gaode_lat=None)
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'bound_pending_collection'
    assert state['diagnostics']['requests'] == 4
    assert responses.paths()[-1] == '/f100/api/search_api/rent'
    assert next(s for s in reg.sources() if s['source'] == 'xingfuli')['community_id'] == 'c1'


def test_name_only_identity_is_rechecked_after_live_verification(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.infos[TOTAL_ID] = info_body(address='西兴路1190号', gaode_lng=None, gaode_lat=None)

    def changed_during_verification(url):
        body = responses(url)
        if urlsplit(url).path == '/f100/api/search_api/rent':
            reg.update('c1', name='另一个花园', aliases=[])
        return body

    state = run(probe(reg, changed_during_verification, tmp_path))
    assert state['stage'] == 'upstream_failed'
    assert '身份信息已变化' in state['message']
    assert not any(s['source'] == 'xingfuli' for s in reg.sources())


def test_ambiguous_candidates_do_not_fetch_entries_until_selected(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses(ambiguous=True)
    svc = probe(reg, responses, tmp_path)
    state = run(svc)
    assert state['stage'] == 'needs_homepage_selection'
    assert state['diagnostics']['requests'] == 5  # Three channels, two identities.
    assert set(responses.paths()) == {'/f100/api/search', '/f100/api/neighborhood/info'}
    assert all(c['rent_total'] is None and c['seeds'] == [] for c in state['candidates'])
    chosen = next(c for c in state['candidates'] if c['neighborhood_id'] == TOTAL_ID)
    before = len(responses.calls)
    svc.select('c1', chosen['candidate_id'], state['revision'])
    svc._thread.join(5)
    assert svc.status('c1')['stage'] == 'bound_pending_collection'
    assert responses.paths()[before:] == [
        '/f100/api/neighborhood/info', '/f100/api/same_neighborhood_rent',
        '/f100/api/search_api/rent']
    assert svc.status('c1')['diagnostics']['requests'] == 3
    assert parse_qs(urlsplit(responses.calls[before + 1]).query)['neighborhood_id'] == [TOTAL_ID]


@pytest.mark.parametrize('budget,last_path', [
    (2, '/f100/api/neighborhood/info'), (3, '/f100/api/same_neighborhood_rent')])
def test_each_new_http_step_respects_budget_without_binding(tmp_path, budget, last_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    state = run(probe(reg, responses, tmp_path, budget=budget))
    assert state['stage'] == 'deferred'
    assert len(responses.calls) == budget and responses.paths()[-1] == last_path
    assert not any(s['source'] == 'xingfuli' and s['status'] == 'matched' for s in reg.sources())


def test_restart_reuses_search_and_info_but_refreshes_identity_and_entry(tmp_path):
    reg = setup(tmp_path)
    first = APIResponses()
    first.entries[TOTAL_ID] = entry_body(items=[], total=0)
    assert run(probe(reg, first, tmp_path))['stage'] == 'entry_not_found'
    second = APIResponses()
    state = run(probe(reg, second, tmp_path))
    assert state['stage'] == 'bound_pending_collection'
    assert state['diagnostics']['cache_hits'] == 2
    assert second.paths() == ['/f100/api/neighborhood/info', '/f100/api/same_neighborhood_rent',
                              '/f100/api/search_api/rent']


def test_failed_entry_is_not_cached_or_mistaken_for_no_entry(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.entries[TOTAL_ID] = json.dumps(dict(status=1001, message='params error'))
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'upstream_failed'
    with reg.db() as db:
        stored = json.loads(db.execute('SELECT value FROM meta WHERE key=?', (PREFIX + 'c1',)).fetchone()[0])
    assert all('rental_entry' not in key for key in stored['steps'])
    assert state['selected_page']['neighborhood_id'] == TOTAL_ID


@pytest.mark.parametrize('rows', [[], [dict(id=SEED, neighborhood_id=OTHER)],
    [dict(id=SEED)], [dict(id=SEED, neighborhood_id=TOTAL_ID), dict(id='2', neighborhood_id=OTHER)],
    [dict(id=True, neighborhood_id=TOTAL_ID)]])
def test_entry_cannot_bypass_live_list_membership_check(tmp_path, rows):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.rental_rows = rows
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'entry_not_found'
    assert f'/zufang/neighbor-house-list/hz-{SEED}.html' not in responses.paths()
    assert not any(s['source'] == 'xingfuli' for s in reg.sources())


def test_bind_uses_a_seed_with_explicit_membership_from_the_live_api(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.rental_rows = [dict(id='123456789', neighborhood_id=TOTAL_ID)]
    state = run(probe(reg, responses, tmp_path, budget=4))
    assert state['stage'] == 'bound_pending_collection'
    source = next(s for s in reg.sources() if s['source'] == 'xingfuli')
    assert source['seed_listing_id'] == '123456789'
    assert len(responses.calls) == 4


def test_list_verification_challenge_stops_in_cooldown_without_binding(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    def challenge(url):
        if urlsplit(url).path == '/f100/api/search_api/rent':
            responses.calls.append(url)
            return '<html>captcha</html>'
        return responses(url)
    state = run(probe(reg, challenge, tmp_path))
    assert state['stage'] == 'cooling_down'
    assert len(responses.calls) == 4
    assert not any(s['source'] == 'xingfuli' for s in reg.sources())


def test_cancel_during_api_membership_check_cannot_bind(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    svc = probe(reg, responses, tmp_path)
    def cancelling(url):
        body = responses(url)
        if urlsplit(url).path == '/f100/api/search_api/rent':
            svc._cancel.set()
        return body
    svc._discovery_factory = lambda **options: XingfuliDiscovery(fetcher=cancelling, **options)
    assert run(svc)['stage'] == 'cancelled'
    assert not any(s['source'] == 'xingfuli' for s in reg.sources())


def test_membership_verification_is_never_reused_from_checkpoint(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    cp = DiscoveryCheckpoint(reg, reg.communities()[0],
        XingfuliDiscovery(directory=tmp_path, fetcher=responses, delay=0),
        threading.Event(), 12, lambda *args: None)
    assert cp.verified_rental_seed(SEED, TOTAL_ID) == SEED
    responses.rental_rows = []
    assert cp.verified_rental_seed(SEED, TOTAL_ID) is None
    assert cp.request_count == 2 and cp.diagnostics['cache_hits'] == 0


@pytest.mark.parametrize('suffix', ['&offset=20', '&search_id=abc', '&callback=x', '&house_id=123'])
def test_list_verification_url_rejects_extra_or_duplicate_parameters(suffix):
    from src.services.xingfuli_rentals import rental_list_api_url
    with pytest.raises(ValueError):
        validate_discovery_url(rental_list_api_url(SEED) + suffix)


def test_api_district_conflict_blocks_automatic_binding_even_with_matching_address(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.infos[TOTAL_ID] = info_body(district_name='萧山区')
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'needs_homepage_selection'
    assert state['candidates'][0]['conflicts']
    assert '/f100/api/same_neighborhood_rent' not in responses.paths()


def test_legacy_homepage_checkpoint_cannot_authorize_new_api_binding(tmp_path):
    reg = setup(tmp_path)
    client = XingfuliDiscovery(directory=tmp_path, fetcher=APIResponses(), delay=0)
    checkpoint = DiscoveryCheckpoint(reg, reg.communities()[0], client, threading.Event(), 12, lambda *args: None)
    old = dict(version=VERSION - 1, fingerprint=checkpoint.fingerprint,
               steps={json.dumps(['homepage', TOTAL_ID]): dict(value={'seeds': [SEED]}, complete=True, expires_at=10**10)})
    with reg.db() as db:
        db.execute('INSERT INTO meta VALUES (?,?)', (PREFIX + 'c1', json.dumps(old)))
    responses = APIResponses()
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'bound_pending_collection' and state['diagnostics']['cache_hits'] == 0
    assert len(responses.calls) == 4


@pytest.mark.parametrize('damage', ['expired', 'city', 'coordinates', 'district'])
def test_damaged_or_expired_api_identity_cache_is_requeried(tmp_path, damage):
    reg = setup(tmp_path)
    responses = APIResponses()
    def checkpoint():
        return DiscoveryCheckpoint(reg, reg.communities()[0],
                                   XingfuliDiscovery(directory=tmp_path, fetcher=responses, delay=0),
                                   threading.Event(), 12, lambda *args: None)
    first = checkpoint()
    first.community_info(TOTAL_ID)
    with reg.db() as db:
        saved = json.loads(db.execute('SELECT value FROM meta WHERE key=?', (PREFIX + 'c1',)).fetchone()[0])
        step = next(iter(saved['steps'].values()))
        if damage == 'expired':
            step['expires_at'] = time.time() - 1
        elif damage == 'city':
            step['value']['city_id'] = 110
        elif damage == 'coordinates':
            step['value']['longitude'] = True
        else:
            step['value']['district'] = None
        db.execute('UPDATE meta SET value=? WHERE key=?', (json.dumps(saved), PREFIX + 'c1'))
    restored = checkpoint()
    assert restored.community_info(TOTAL_ID)['city_id'] == 1853
    assert restored.request_count == 1 and restored.diagnostics['cache_hits'] == 0


def test_restored_candidate_must_recheck_api_district_before_fetching_entry(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses(ambiguous=True)
    svc = probe(reg, responses, tmp_path)
    state = run(svc)
    chosen = next(c for c in state['candidates'] if c['neighborhood_id'] == TOTAL_ID)
    responses.infos[TOTAL_ID] = info_body(district_name='萧山')
    svc.select('c1', chosen['candidate_id'], state['revision'])
    svc._thread.join(5)
    assert svc.status('c1')['stage'] == 'needs_homepage_selection'
    assert '/f100/api/same_neighborhood_rent' not in responses.paths()


def test_cancel_before_rental_entry_prevents_next_http_and_binding(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    svc = probe(reg, responses, tmp_path)
    original = responses.__call__
    def cancel_after_identity(url):
        body = original(url)
        if urlsplit(url).path == '/f100/api/neighborhood/info':
            svc._cancel.set()
        return body
    svc._discovery_factory = lambda **options: XingfuliDiscovery(fetcher=cancel_after_identity, **options)
    state = run(svc)
    assert state['stage'] == 'cancelled'
    assert '/f100/api/same_neighborhood_rent' not in responses.paths()


def test_api_verification_response_enters_existing_cooldown(tmp_path):
    reg = setup(tmp_path)
    responses = APIResponses()
    responses.entries[TOTAL_ID] = '<html>captcha</html>'
    state = run(probe(reg, responses, tmp_path))
    assert state['stage'] == 'cooling_down'
    assert len(responses.calls) == 3


@pytest.mark.parametrize('changes', [dict(id=OTHER), dict(city_id=110), dict(name=''),
                                    dict(address=None), dict(gaode_lng='NaN'),
                                    dict(gaode_lat=91), dict(gaode_lat=True)])
def test_invalid_api_identity_is_rejected(changes):
    with pytest.raises(ValueError):
        parse_community_info(info_body(**changes), TOTAL_ID)


@pytest.mark.parametrize('body', ['{}', '[]', '<html>failure</html>',
                                 '{"status":0,"data":[]}', '{"status":false,"data":{}}'])
def test_bad_api_envelope_cannot_supply_identity_or_entry(body):
    for parse in (parse_community_info, parse_rental_entry):
        with pytest.raises(ValueError):
            parse(body, TOTAL_ID)


@pytest.mark.parametrize('body', [
    entry_body(items=[], total=3), entry_body(items=[{}]),
    entry_body(items=[dict(id=SEED, neighborhood_id=OTHER)]),
    entry_body(total=True), entry_body(more='true')])
def test_invalid_entry_is_not_a_successful_empty_result(body):
    with pytest.raises(ValueError):
        parse_rental_entry(body, TOTAL_ID)


@pytest.mark.parametrize('url', [
    '/f100/api/neighborhood/info?neighborhood_id=123&extra=1',
    '/f100/api/neighborhood/info?neighborhood_id=123&neighborhood_id=456',
    '/f100/api/neighborhood/info?neighborhood_id=abc',
    '/f100/api/neighborhood/info',
    '/f100/api/same_neighborhood_rent?neighborhood_id=123&city_id=110&offset=0&count=10',
    '/f100/api/same_neighborhood_rent?neighborhood_id=123&city_id=1853&offset=20&count=10',
    '/f100/api/same_neighborhood_rent?neighborhood_id=123&city_id=1853&offset=0&count=100'])
def test_new_api_whitelist_rejects_unverified_parameters(url):
    with pytest.raises(ValueError):
        validate_discovery_url('https://m.xflapp.com' + url)
