import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from src.services import directory_collection, tmsf_fetcher
from src.services.community_registry import CommunityRegistry
from src.services.tmsf_property_type import extract_property_type, fetch_property_facts


def page(name='测试花园', prop='住宅'):
    return f'<input id="communityname_auto" value="{name}"><input id="managetypename_auto" value="{prop}">'


@pytest.mark.parametrize('prop', ['住宅', '写字楼', '住宅/写字楼', '非住宅', '公寓'])
def test_extraction_keeps_explicit_and_mixed_types(prop):
    assert extract_property_type(page(prop=prop)) == prop


def test_text_fallback_and_challenge_are_distinct():
    assert extract_property_type('<p>物业类型：住宅</p>') == '住宅'
    assert extract_property_type('<html>请完成验证</html>') is None


def test_full_title_accepts_abbreviated_body_name():
    html = '<title>同人春江时代花园 -小区详情-透明售房网</title>' + page('春江时代花园')
    client = SimpleNamespace(fetch_text=lambda *_: html)
    assert fetch_property_facts(client, '600', ['同人春江时代花园'])['property_type'] == '住宅'


@pytest.mark.parametrize('html', [page(name='另一个小区'), '<html>请完成验证</html>', page(prop='')])
def test_facts_reject_wrong_community_challenge_and_missing_type(html):
    client = SimpleNamespace(fetch_text=lambda *_: html)
    with pytest.raises(ValueError):
        fetch_property_facts(client, '1', ['测试花园'])


def setup_collection(monkeypatch, response):
    from scripts import fetch_tmsf_binjiang_communities as listing
    community = SimpleNamespace(community_id='1', community_name='测试花园', community_alias=None,
                                district='滨江', subdistrict='长河', source_url='https://www.tmsf.com/list.js')
    monkeypatch.setattr(listing, 'fetch_binjiang_communities', lambda: [community])
    calls, closed = [], []
    class Client:
        def fetch_text(self, url, timeout):
            calls.append(url)
            if isinstance(response, Exception):
                raise response
            return response
        def close(self): closed.append(True)
    monkeypatch.setattr(tmsf_fetcher, 'TmsfClient', Client)
    monkeypatch.setattr(directory_collection, 'pause', lambda _: None)
    return calls, closed


def test_integrated_types_survive_restart_and_second_hand_counts_refresh(tmp_path, monkeypatch):
    calls, closed = setup_collection(monkeypatch, page())
    path = tmp_path / 'registry.sqlite3'
    store = CommunityRegistry(path)
    report = directory_collection.collect_names(store, ['tmsf'])
    assert report['phase'] == 'succeeded' and report['new'] == 1 and report['pending'] == 1
    assert report['property_types'] == 1 and len(calls) == 1
    source = CommunityRegistry(path).sources()[0]
    assert source['property_type'] == '住宅' and source['property_type_captured_at']
    assert source['property_type_url'].endswith('xq_indexnew_1.htm')
    assert not any(k.startswith('_') for k in source)
    again = directory_collection.collect_names(CommunityRegistry(path), ['tmsf'])
    assert again['property_types'] == 1 and again['existing'] == 1
    assert len(calls) == 2 and len(closed) == 2


def test_type_failure_preserves_old_fact_and_retries_on_next_collection(tmp_path, monkeypatch):
    calls, _ = setup_collection(monkeypatch, RuntimeError('request failed'))
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.ingest(dict(source='tmsf', source_id='1', name='测试花园', district='滨江',
                      property_type='住宅', property_type_captured_at='2020-01-01T00:00:00+00:00'))
    report = directory_collection.collect_names(store, ['tmsf'])
    assert report['phase'] == 'partial_failed' and report['property_types_failed'] == 1
    assert report['existing'] == 1 and report['errors'][0]['stage'] == 'property_type'
    source = store.sources()[0]
    assert source['property_type'] == '住宅' and source['property_type_error']
    assert source['property_type_captured_at'].startswith('2020')
    directory_collection.collect_names(store, ['tmsf'])
    assert len(calls) == 4


def test_deleted_tmsf_source_never_requests_property_details(tmp_path, monkeypatch):
    calls, _ = setup_collection(monkeypatch, page())
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    item = store.ingest(dict(source='tmsf', source_id='1', name='测试花园', district='滨江'))
    store.ignore_source(item['id'])
    report = directory_collection.collect_names(store, ['tmsf'])
    assert report['ignored'] == 1 and report['property_types'] == 0 and not calls


def test_failed_refresh_preserves_existing_standalone_type(tmp_path, monkeypatch):
    import json
    setup_collection(monkeypatch, RuntimeError('blocked'))
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    store.ingest(dict(source='tmsf', source_id='1', name='测试花园', district='滨江'))
    (tmp_path / 'property_types.json').write_text(json.dumps({'1': {'property_type': '住宅',
        'url': 'https://www.tmsf.com/esf/xq_indexnew_1.htm'}}))
    report = directory_collection.collect_names(store, ['tmsf'])
    assert report['phase'] == 'partial_failed'
    source = store.sources()[0]
    assert source['property_type'] == '住宅' and source['property_type_error']
    assert source['property_type_url'].endswith('xq_indexnew_1.htm')


def test_cancel_after_name_keeps_candidate_without_detail_request(tmp_path, monkeypatch):
    calls, closed = setup_collection(monkeypatch, page())
    store = CommunityRegistry(tmp_path / 'registry.sqlite3')
    cancel = threading.Event()
    def progress(report):
        if report['new']:
            cancel.set()
    def pause(event):
        directory_collection.check(event)
    monkeypatch.setattr(directory_collection, 'pause', pause)
    report = directory_collection.collect_names(store, ['tmsf'], cancel=cancel, progress=progress)
    assert report['phase'] == 'cancelled' and report['running'] is False
    assert len(store.sources()) == 1 and not calls and closed


def test_property_cli_runs_with_shared_imports():
    result = subprocess.run([sys.executable, 'scripts/fetch_tmsf_property_type.py', '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
