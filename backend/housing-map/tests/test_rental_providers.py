"""Provider selection and snapshot isolation use actual directory/storage objects."""
import datetime as dt
import time

from src.services.community_registry import CommunityRegistry
from src.services.directory_policy import KEY, VERSION
from src.services.rental_reference import providers
from src.services.rental_reference.refresh import RentalRefreshService, load_verified_mappings
from src.services.rental_reference.storage import CommunityBatch, load_current, publish_run
from src.services.rental_reference.crawl_types import SeedRunResult


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
                       address='月明路1076号', seed_listing_id=sid,
                       auto_association_disabled=True, source_url='https://m.xflapp.com/zufang/neighbor-house-list/hz-123.html'))
    if kind == 'fang':
        # A retired Fang association can only exist as historical data: write it
        # straight into the ledger, the registry refuses new Fang associations.
        with reg.db() as db:
            db.execute("UPDATE sources SET cid=?,status='matched',method='manual' WHERE id=?",
                       ('pilot', r['id']))
    else:
        reg.associate(r['id'], 'pilot')
    return r


def test_historical_fang_is_never_current():
    assert not providers.same_source({'source': 'fang', 'source_community_id': '7'}, 'xingfuli', '7')
    assert not providers.same_source({'source_community_id': '7'}, 'xingfuli', '7')
    assert providers.same_source({'source': 'xingfuli', 'source_community_id': '7'}, 'xingfuli', '7')


def test_only_xingfuli_is_an_active_source_and_unlink_does_not_fall_back(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'fang')
    x = source(reg, 'xingfuli')
    assert providers.active_sources(reg)['pilot']['source'] == 'xingfuli'
    assert load_verified_mappings(tmp_path / 'rental_community_mappings.json') == [('123', 'pilot')]
    reg.unlink(x['id'])
    # No current source remains; the historical Fang association never returns.
    assert providers.active_sources(reg) == {}
    assert load_verified_mappings(tmp_path / 'rental_community_mappings.json') == []


def test_legacy_fang_mapping_file_is_not_imported(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'fang')
    (tmp_path / 'rental_community_mappings.json').write_text(
        '{"version": 1, "mappings": [{"source": "fang", "source_community_id": "123",'
        ' "community_id": "pilot", "status": "verified"}]}', encoding='utf-8')
    assert load_verified_mappings(tmp_path / 'rental_community_mappings.json') == []
    assert providers.active_sources(reg) == {}


def test_cross_provider_same_id_cannot_be_carried_or_reused(tmp_path):
    now = dt.datetime.now(dt.UTC).isoformat()
    def batch(cid, provider, status='complete'):
        return CommunityBatch(cid, provider, '123', status, now, samples=[])
    publish_run(tmp_path, [batch('pilot', 'fang')])
    publish_run(tmp_path, [batch('pilot', 'xingfuli', 'list_failed'), batch('other', 'xingfuli')])
    assert 'pilot' not in load_current(tmp_path)['communities']
    assert not providers.same_source(dict(source='fang', source_community_id='123'), 'xingfuli', '123')


def test_xingfuli_job_publishes_without_any_fang_request(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'fang')
    source(reg, 'xingfuli')
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
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                   xingfuli_factory=Client, delay=0)
    service.start()
    limit = time.monotonic() + 5
    while service.status()['running'] and time.monotonic() < limit:
        time.sleep(.01)
    job = service.status()
    assert job['phase'] == 'done', job
    assert calls == [('123', '123')]
    published = load_current(tmp_path / 'rentals')['communities']
    assert set(published) == {'pilot'}
    assert published['pilot']['source'] == 'xingfuli'


def test_query_and_coverage_do_not_read_another_provider_snapshot(tmp_path, monkeypatch):
    from src.api import rental_routes
    from src.services.directory_coverage import attach_coverage
    reg = registry(tmp_path)
    source(reg, 'fang')
    source(reg, 'xingfuli')
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


def test_fang_association_is_not_collected_and_cached_run_stays_stable(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'xingfuli')
    c = reg.create('其他花园', district='滨江', address='测试路1号', community_id='other')
    t = reg.ingest(dict(source='tmsf', source_id='t2', name='其他花园', district='滨江',
                        address='测试路1号', property_type='住宅', listing_count=3, market_state='second_hand'))
    reg.associate(t['id'], c['community_id'])
    f = reg.ingest(dict(source='fang', source_id='456', name='其他花园', district='滨江',
                        address='测试路1号', auto_association_disabled=True))
    with reg.db() as db:
        db.execute("UPDATE sources SET cid=?,status='matched',method='manual' WHERE id=?",
                   (c['community_id'], f['id']))
    crawled = []

    class XClient:
        request_count = 2
        cooldown_until = None
        def __init__(self, **kwargs): pass
        def crawl(self, sid, seed, **kwargs):
            crawled.append(sid)
            return SeedRunResult(seed=providers.source_url(providers.active_sources(reg)['pilot']),
                                 status='empty_ok', pages_fetched=1)
        def close(self): pass

    path = tmp_path / 'rental_community_mappings.json'
    service = RentalRefreshService(tmp_path / 'rentals', path, xingfuli_factory=XClient, delay=0)
    service.start(); service._thread.join(5)
    assert service.status()['phase'] == 'done', service.status()
    assert service.status()['processed_communities'] == 1
    assert crawled == ['123']
    first = load_current(tmp_path / 'rentals')
    assert {e['source'] for e in first['communities'].values()} == {'xingfuli'}

    def forbidden(**kwargs):
        raise AssertionError('cached run must not request upstream')
    second = RentalRefreshService(tmp_path / 'rentals', path, xingfuli_factory=forbidden, delay=0)
    second.start(); second._thread.join(5)
    assert second.status()['reused_communities'] == 1
    assert load_current(tmp_path / 'rentals') == first


def test_changed_association_during_xingfuli_crawl_is_not_published(tmp_path):
    reg = registry(tmp_path)
    source(reg, 'fang')
    x = source(reg, 'xingfuli')
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
