"""Provider selection and snapshot isolation use actual directory/storage objects."""
import datetime as dt
import time

from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION
from src.services.rental_reference import providers
from src.services.rental_reference.refresh import RentalRefreshService, load_verified_mappings
from src.services.rental_reference.storage import CommunityBatch, load_current, publish_run
from src.services.fang_rentals import SeedRunResult


def registry(tmp_path):
    reg = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    c = reg.create('风雅钱塘', district='滨江', address='月明路1076号', community_id='pilot')
    t = reg.ingest(dict(source='tmsf', source_id='t1', name='风雅钱塘', district='滨江',
                        address='月明路1076号', property_type='住宅', listing_count=3, market_state='second_hand'))
    reg.associate(t['id'], c['community_id'])
    with reg.db() as db:
        db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
    return reg


def source(reg, kind, sid='123'):
    r = reg.ingest(dict(source=kind, source_id=sid, name='风雅钱塘', district='滨江',
                       address='月明路1076号', seed_listing_id='7502229388495274018',
                       auto_association_disabled=True, source_url='https://m.xflapp.com/zufang/neighbor-house-list/hz-7502229388495274018.html'))
    reg.associate(r['id'], 'pilot')
    return r


def test_preferred_source_and_explicit_unlink(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'fang'); x = source(reg, 'xingfuli')
    assert providers.active_sources(reg)['pilot']['source'] == 'xingfuli'
    assert load_verified_mappings(tmp_path / 'rental_community_mappings.json') == [('123', 'pilot')]
    reg.unlink(x['id'])
    assert providers.active_sources(reg)['pilot']['source'] == 'fang'


def test_source_manager_removes_active_provider_and_preserves_fang(tmp_path):
    import pytest
    from src.services.rental_reference.sources import SourceStore
    reg = registry(tmp_path); source(reg, 'fang'); source(reg, 'xingfuli')
    store = SourceStore(tmp_path / 'rental_community_mappings.json')
    assert store.all_mappings()['pilot']['source'] == 'xingfuli'
    with pytest.raises(ValueError, match='先解除'):
        store.confirm('pilot', '123')
    store.remove('pilot')
    assert store.all_mappings()['pilot']['source'] == 'fang'


def test_cross_provider_same_id_cannot_be_carried_or_reused(tmp_path):
    now = dt.datetime.now(dt.UTC).isoformat()
    def batch(cid, provider, status='complete'):
        return CommunityBatch(cid, provider, '123', status, now, samples=[])
    publish_run(tmp_path, [batch('pilot', 'fang')])
    publish_run(tmp_path, [batch('pilot', 'xingfuli', 'list_failed'), batch('other', 'fang')])
    assert 'pilot' not in load_current(tmp_path)['communities']
    assert not providers.same_source(dict(source='fang', source_community_id='123'), 'xingfuli', '123')


def test_xingfuli_job_publishes_without_using_fang_client(tmp_path):
    reg = registry(tmp_path); source(reg, 'fang'); source(reg, 'xingfuli')
    calls = []
    class Client:
        request_count = 2
        cooldown_until = None
        def __init__(self, **kwargs): pass
        def crawl(self, sid, seed, **kwargs):
            calls.append((sid, seed))
            return SeedRunResult(seed=providers.source_url(providers.active_sources(reg)['pilot']), samples=[],
                                 pages_fetched=1, status='empty_ok')
        def close(self): pass
    def forbidden(**kwargs):
        raise AssertionError('Fang must not be constructed for a Xingfuli-only job')
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                   fetch_factory=forbidden, xingfuli_factory=Client, delay=0)
    service.start()
    limit = time.monotonic() + 5
    while service.status()['running'] and time.monotonic() < limit:
        time.sleep(.01)
    job = service.status()
    assert job['phase'] == 'done', job
    assert calls == [('123', '7502229388495274018')]
    assert load_current(tmp_path / 'rentals')['communities']['pilot']['source'] == 'xingfuli'


def test_query_and_coverage_do_not_read_another_provider_snapshot(tmp_path, monkeypatch):
    from src.api import rental_routes
    from src.services.directory_coverage import attach_coverage
    reg = registry(tmp_path); source(reg, 'fang'); source(reg, 'xingfuli')
    monkeypatch.setattr(rental_routes, '_mappings_path', tmp_path / 'rental_community_mappings.json')
    now = dt.datetime.now(dt.UTC).isoformat()
    entry = dict(source='fang', source_community_id='123', captured_at=now, status='complete', samples=[])
    assert rental_routes._mapped_entry({'communities': {'pilot': entry}}, 'pilot', {'pilot': '123'}) is None
    entry['source'] = 'xingfuli'
    assert rental_routes._mapped_entry({'communities': {'pilot': entry}}, 'pilot', {'pilot': '123'}) == entry
    assert rental_routes._source_links('pilot', '123') == [providers.source_url(providers.active_sources(reg)['pilot'])]
    publish_run(tmp_path / 'rentals', [CommunityBatch('pilot', 'fang', '123', 'empty_ok', now)])
    coverage = attach_coverage([{'community_id': 'pilot'}], reg, tmp_path)[0]['coverage']['rental']
    assert coverage['state'] == 'pending' and coverage['captured_at'] is None


def test_mixed_provider_publication_and_cached_second_run(tmp_path):
    reg = registry(tmp_path); source(reg, 'xingfuli')
    c = reg.create('其他花园', district='滨江', address='测试路1号', community_id='other')
    t = reg.ingest(dict(source='tmsf', source_id='t2', name='其他花园', district='滨江',
                        address='测试路1号', property_type='住宅', listing_count=3, market_state='second_hand'))
    reg.associate(t['id'], c['community_id'])
    f = reg.ingest(dict(source='fang', source_id='456', name='其他花园', district='滨江',
                        address='测试路1号', auto_association_disabled=True))
    reg.associate(f['id'], c['community_id'])
    class XClient:
        request_count = 2
        cooldown_until = None
        def __init__(self, **kwargs): pass
        def crawl(self, sid, seed, **kwargs):
            return SeedRunResult(seed=providers.source_url(providers.active_sources(reg)['pilot']),
                                 status='empty_ok', pages_fetched=1)
        def close(self): pass
    class FClient:
        def __init__(self, **kwargs): pass
        def fetch(self, url): return '房天下 暂无房源'
        def close(self): pass
    path = tmp_path / 'rental_community_mappings.json'
    service = RentalRefreshService(tmp_path / 'rentals', path, fetch_factory=FClient,
                                   xingfuli_factory=XClient, delay=0)
    service.start(); service._thread.join(5)
    assert service.status()['phase'] == 'done', service.status()
    assert service.status()['processed_communities'] == 2
    assert service.status()['request_count'] == 3
    first = load_current(tmp_path / 'rentals')
    assert {e['source'] for e in first['communities'].values()} == {'fang', 'xingfuli'}
    def forbidden(**kwargs): raise AssertionError('cached run must not request upstream')
    second = RentalRefreshService(tmp_path / 'rentals', path, fetch_factory=forbidden,
                                  xingfuli_factory=forbidden, delay=0)
    second.start(); second._thread.join(5)
    assert second.status()['reused_communities'] == 2
    assert load_current(tmp_path / 'rentals') == first


def test_changed_association_during_xingfuli_crawl_is_not_published(tmp_path):
    reg = registry(tmp_path); source(reg, 'fang'); x = source(reg, 'xingfuli')
    class Client:
        request_count = 1
        cooldown_until = None
        def __init__(self, **kwargs): pass
        def crawl(self, sid, seed, **kwargs):
            reg.unlink(x['id'])
            return SeedRunResult(seed=x['source_url'], status='empty_ok', pages_fetched=1)
        def close(self): pass
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                   xingfuli_factory=Client, delay=0)
    service.start(); service._thread.join(5)
    assert not service.status()['running']
    assert service.status()['result']['reason'] == 'sources_changed'
    assert load_current(tmp_path / 'rentals') is None
