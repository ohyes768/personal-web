"""Confirmed new projects never enter rental platform workflows."""
import pytest

from tests.test_rental_probe import setup, FakeDiscovery
from src.services.community_registry import dump
from src.services.directory_policy import KEY, VERSION
from src.services.rental_reference.association import eligible_communities
from src.services.rental_reference.matching import SourceMatchingService, source_reviews
from src.services.rental_reference.probe import ProbeService, ProbeInvalid


def project(registry, status, directory):
    record = next(r for r in registry.sources() if r['source'] == 'tmsf')
    record.update(market_state='new_house', project_sale_status=status)
    with registry.db() as db:
        db.execute('UPDATE sources SET payload=? WHERE id=?', (dump(record), record['id']))
        if directory:
            db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (KEY, VERSION))
            admission = registry.pending_admission()
            admission.update(state='admitted', decision_kind='manual')
            db.execute('UPDATE community_admission SET payload=? WHERE cid=?', (dump(admission), 'c1'))


@pytest.mark.parametrize('directory', [False, True])
@pytest.mark.parametrize('status', ['在售', '尾盘', '待售'])
def test_newhouse_has_no_rental_targets_or_platform_requests(tmp_path, directory, status):
    registry = setup(tmp_path)
    project(registry, status, directory)
    fake = FakeDiscovery()
    svc = SourceMatchingService(registry, directory=tmp_path / 'rentals',
                                discovery_factory=lambda **kw: fake, delay=0)
    assert eligible_communities(registry)[0] == []
    assert source_reviews(registry) == []
    # Include a persisted pending target, as on restart/continue after reclassification.
    svc._job['remaining'] = ['c1']
    for mode in ['full', 'incremental']:
        svc.start(mode=mode)
        svc._thread.join(5)
        assert svc.status()['total'] == 0
        assert not svc.status()['running']
    probe = ProbeService(registry, directory=tmp_path / 'rentals',
                         discovery_factory=lambda **kw: fake, delay=0)
    with pytest.raises(ProbeInvalid):
        probe.start('c1')
    assert fake.calls == []
    assert len(registry.sources()) == 1


@pytest.mark.parametrize('directory', [False, True])
def test_sold_out_legacy_newhouse_reenters_rental_targets(tmp_path, directory):
    registry = setup(tmp_path)
    project(registry, '售完', directory)
    assert [c['community_id'] for c in eligible_communities(registry)[0]] == ['c1']
    svc = SourceMatchingService(registry, directory=tmp_path / 'rentals', delay=0)
    assert svc._targets('full') == svc._targets('incremental') == ['c1']


@pytest.mark.parametrize('directory', [False, True])
def test_newhouse_filter_preserves_existing_rental_association(tmp_path, directory):
    registry = setup(tmp_path)
    rental = registry.ingest(dict(source='xingfuli', source_id='123', name='测试花园',
                                  district='滨江', auto_association_disabled=True))
    registry.associate(rental['id'], 'c1')
    project(registry, '在售', directory)
    before = registry.sources()
    assert eligible_communities(registry)[0] == []
    assert source_reviews(registry) == []
    assert registry.sources() == before
