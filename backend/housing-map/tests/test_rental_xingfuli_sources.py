"""Automatic matching binds only what the platform actually proves."""
import pytest

from src.services.community_registry import CommunityRegistry
from src.services.rental_reference.xingfuli_sources import auto_discover, evaluate

TOTAL_ID = '6581009489657331972'
PHASE_ID = '6598511715770433795'
SEED = '7406856173871235098'


def setup(tmp_path, name='测试花园', address='测试路1号'):
    registry = CommunityRegistry(tmp_path / 'community_registry.sqlite3')
    registry.create(name, district='滨江', address=address, community_id='c1',
                    longitude=120.188369, latitude=30.203001, coordinate_system='gcj02')
    record = registry.ingest(dict(source='tmsf', source_id='c1', name=name, district='滨江',
                                  address=address, property_type='住宅',
                                  market_state='second_hand', listing_count=3))
    registry.associate(record['id'], 'c1')
    return registry


class FakeDiscovery:
    def __init__(self, *, search=None, homepages=None, owners=None, lists=None):
        self.request_count = 0
        self.calls = []
        self._search = search or {}
        self._homepages = homepages or {}
        self._owners = owners or {}
        self._lists = lists if lists is not None else {}

    def search(self, name, channel):
        self.request_count += 1
        self.calls.append(('search', name, channel))
        found = self._search.get((name, channel), self._search.get(name, {}))
        return {nid: {'name': platform_name, 'seeds': list(seeds)}
                for nid, (platform_name, seeds) in found.items()}

    def homepage(self, neighborhood_id):
        self.request_count += 1
        self.calls.append(('homepage', neighborhood_id))
        return self._homepages[neighborhood_id]

    def listing_owner(self, seed):
        self.request_count += 1
        self.calls.append(('listing', seed))
        return self._owners.get(seed)

    def listing_owner_from_list(self, seed, neighborhood_id):
        self.request_count += 1
        self.calls.append(('list', seed))
        return self._lists.get(seed) == neighborhood_id


def homepage(neighborhood_id=TOTAL_ID, name='测试花园', address='测试路1号', seeds=(SEED,),
             longitude=120.188369, latitude=30.203001):
    return {'neighborhood_id': neighborhood_id, 'name': name, 'address': address,
            'longitude': longitude, 'latitude': latitude, 'coordinate_system': 'gcj02',
            'rent_total': 31, 'seeds': list(seeds)}


def test_exact_name_and_matching_place_binds(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('测试花园', [SEED])}},
        homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 1 and report['pending'] == 0
    source = next(s for s in registry.sources() if s['source'] == 'xingfuli')
    assert source['status'] == 'matched' and source['community_id'] == 'c1'
    assert source['source_id'] == TOTAL_ID and source['seed_listing_id'] == SEED


def test_a_position_match_binds_although_the_address_wording_differs(tmp_path):
    """The platform writes its own address; the position decides."""
    registry = setup(tmp_path, address='浙江省杭州市滨江区测试路1号')
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('测试花园', [SEED])}},
        homepages={TOTAL_ID: homepage(address='测试路1号')},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 1
    source = next(s for s in registry.sources() if s['source'] == 'xingfuli')
    # The platform address stays the source's own fact and never becomes the
    # community's address evidence.
    assert source['platform_address'] == '测试路1号'
    assert not source.get('address')
    assert registry.communities()[0]['address'] == '浙江省杭州市滨江区测试路1号'


def test_a_seed_of_another_community_is_never_bound(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('测试花园', [SEED])}},
        homepages={TOTAL_ID: homepage()}, owners={SEED: '6581009489657331973'},
        lists={SEED: TOTAL_ID})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 0
    assert not any(s['source'] == 'xingfuli' and s['status'] == 'matched' for s in registry.sources())


def test_a_seed_whose_list_belongs_elsewhere_is_never_bound(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('测试花园', [SEED])}},
        homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID},
        lists={SEED: '6581009489657331973'})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 0
    assert not any(s['source'] == 'xingfuli' and s['status'] == 'matched' for s in registry.sources())


def test_a_phase_variant_is_never_bound_automatically(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {PHASE_ID: ('测试花园(南区)', [SEED])}},
        homepages={PHASE_ID: homepage(neighborhood_id=PHASE_ID, name='测试花园(南区)')},
        owners={SEED: PHASE_ID}, lists={SEED: PHASE_ID})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 0 and report['pending'] == 1
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())


def test_a_different_name_is_never_bound_automatically(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('幸福人家', [SEED])}},
        homepages={TOTAL_ID: homepage(name='幸福人家')}, owners={SEED: TOTAL_ID},
        lists={SEED: TOTAL_ID})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 0
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())


def test_a_far_away_match_is_not_bound(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('测试花园', [SEED])}},
        homepages={TOTAL_ID: homepage(address='测试路9号', longitude=120.30, latitude=30.30)},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    report = auto_discover(registry, fake, registry.communities())
    assert report['matched'] == 0 and report['pending'] == 1


def test_a_community_with_a_source_is_left_alone(tmp_path):
    registry = setup(tmp_path)
    registry.ingest(dict(source='fang', source_id='f1', name='测试花园', district='滨江',
                         address='测试路1号'))
    fake = FakeDiscovery(search={}, homepages={})
    report = auto_discover(registry, fake, registry.communities())
    assert report['checked'] == 0 and fake.calls == []


def test_the_request_budget_is_respected(tmp_path):
    registry = setup(tmp_path)
    other = '6581009489657331973'
    fake = FakeDiscovery(
        search={('测试花园', 'second_hand'): {TOTAL_ID: ('测试花园', [SEED])},
                ('其他', 'second_hand'): {other: ('其他', [SEED])}},
        homepages={TOTAL_ID: homepage(), other: homepage(neighborhood_id=other, name='其他')},
        owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    report = auto_discover(registry, fake, registry.communities(), budget=2)
    assert fake.request_count <= 2
    assert report['matched'] == 0 and report['deferred'] == 1


def test_the_budget_keeps_checking_the_next_community_next_round(tmp_path):
    """A bounded budget must not spend every round on the same community."""
    registry = setup(tmp_path)
    registry.create('第二个花园', district='滨江', address='测试路2号', community_id='c2',
                    longitude=120.188369, latitude=30.203001, coordinate_system='gcj02')
    record = registry.ingest(dict(source='tmsf', source_id='c2', name='第二个花园', district='滨江',
                                  address='测试路2号', property_type='住宅',
                                  market_state='second_hand', listing_count=3))
    registry.associate(record['id'], 'c2')
    communities = registry.communities()
    first = FakeDiscovery(search={}, homepages={})
    report = auto_discover(registry, first, communities, budget=2)
    assert report['checked'] == 1 and report['missing'] == 1 and report['deferred'] == 1
    second = FakeDiscovery(search={}, homepages={})
    report = auto_discover(registry, second, communities, budget=2)
    assert report['checked'] == 1 and report['missing'] == 1
    # The second round visited the other community, not the first one again.
    assert second.calls[0][1] == '第二个花园'


def test_evaluate_reports_the_gaps_of_a_weak_candidate():
    community = {'community_name': '测试花园', 'district': '滨江', 'address': '测试路1号',
                 'longitude': 120.188369, 'latitude': 30.203001, 'coordinate_system': 'gcj02'}
    judgement = evaluate(community, {'name': '测试花园', 'address': '别的路2号',
                                      'longitude': 120.30, 'latitude': 30.30,
                                      'coordinate_system': 'gcj02'})
    assert not judgement['strong']
    assert '缺少一致地址或位置证据' in judgement['gaps']
    assert not judgement['conflicts']


def test_the_refresh_run_binds_a_proven_source(tmp_path):
    from src.services.rental_reference.refresh import RentalRefreshService
    registry = setup(tmp_path)
    fake = FakeDiscovery(
        search={('测试花园', 'rent'): {TOTAL_ID: ('测试花园', [SEED])}},
        homepages={TOTAL_ID: homepage()}, owners={SEED: TOTAL_ID}, lists={SEED: TOTAL_ID})
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                   delay=0, auto_discover=True,
                                   discovery_factory=lambda **kwargs: fake)
    service.start()
    service._thread.join(5)
    assert not service.status()['running']
    source = next(s for s in registry.sources() if s['source'] == 'xingfuli')
    assert source['status'] == 'matched' and source['community_id'] == 'c1'


def test_the_refresh_run_stays_offline_without_the_switch(tmp_path):
    from src.services.rental_reference.refresh import RentalRefreshService
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={}, homepages={})
    service = RentalRefreshService(tmp_path / 'rentals', tmp_path / 'rental_community_mappings.json',
                                   delay=0, discovery_factory=lambda **kwargs: fake)
    service.start()
    service._thread.join(5)
    assert fake.calls == []
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())
