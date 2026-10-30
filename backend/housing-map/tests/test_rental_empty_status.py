"""Empty stock is distinct from source lookup or verification failure."""
from tests.test_rental_probe import setup, FakeDiscovery, homepage, TOTAL_ID, service, run
from src.services.rental_reference.matching import SourceMatchingService, source_reviews
from src.services.rental_reference import probe


def test_empty_rentals_have_their_own_review_category(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={'测试花园': {TOTAL_ID: '测试花园'}},
                         homepages={TOTAL_ID: homepage(seeds=(), total=0)})
    state = run(service(registry, fake, tmp_path))
    assert state['stage'] == probe.STAGE_NO_LISTINGS
    review = source_reviews(registry)[0]
    assert review['reason'] == 'no_listings'
    assert '暂无在租房源' in review['message']
    assert not any(s['source'] == 'xingfuli' for s in registry.sources())


def test_empty_rentals_do_not_count_as_batch_failure(tmp_path):
    registry = setup(tmp_path)
    fake = FakeDiscovery(search={'测试花园': {TOTAL_ID: '测试花园'}},
                         homepages={TOTAL_ID: homepage(seeds=(), total=0)})
    svc = SourceMatchingService(registry, directory=tmp_path/'rentals',
                                discovery_factory=lambda **kwargs: fake, delay=0)
    svc.start(mode='full'); svc._thread.join(5)
    status = svc.status()
    assert not status['running']
    assert status['association']['failed'] == 0
    assert status['association']['missing'] == 1
    assert 'c1' not in svc._targets('incremental')
