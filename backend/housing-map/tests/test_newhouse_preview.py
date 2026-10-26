"""The live preview may only mutate its disposable copy, never its input registry."""
import hashlib
from types import SimpleNamespace

from scripts.preview_newhouse_browser import preview
from src.services.community_registry import CommunityRegistry


def test_preview_keeps_registry_bytes_and_evidence_read_only(tmp_path):
    path = tmp_path / 'registry.sqlite3'
    store = CommunityRegistry(path)
    store.ingest(dict(source='tmsf', source_kind='project', source_id='123', name='测试园',
        project_id='123', project_siteid='33', district='滨江'))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    html = '''<div class="house_float_name_title">测试园</div><a id="districtname">滨江楼盘</a>
    <span class="house_information_price_residence">住宅</span>
    <span class="house_float_name_tips_greenlight">在售</span>
    <div>楼盘地址</div><div>滨江区测试路1号</div>'''
    report = preview(path, client=SimpleNamespace(fetch_text=lambda *_: html))
    assert report['mode'] == 'read_only_source_evidence'
    assert report['counts'] == {'residential_evidence_ready': 1}
    assert report['items'][0]['association'] == 'new_candidate'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert not store.sources()[0].get('property_type')
    assert not store.communities()
