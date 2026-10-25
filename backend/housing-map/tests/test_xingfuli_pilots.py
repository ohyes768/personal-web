import hashlib

from tests.test_rental_providers import registry
from src.services import xingfuli_pilots as pilots
from src.services.rental_reference.providers import active_sources


def test_preview_is_read_only_and_apply_is_idempotent(tmp_path):
    reg = registry(tmp_path)
    before = hashlib.sha256(reg.path.read_bytes()).hexdigest()
    report = pilots.preview(pilots.ReadOnlyRegistry(reg.path))
    assert report[0]['status'] == 'ready'
    assert hashlib.sha256(reg.path.read_bytes()).hexdigest() == before
    pilots.apply(reg)
    assert active_sources(reg)['pilot']['source'] == 'xingfuli'
    count = len(reg.sources())
    pilots.apply(reg)
    assert len(reg.sources()) == count


def test_explicit_unlink_is_not_undone(tmp_path):
    reg = registry(tmp_path); pilots.apply(reg)
    bound = active_sources(reg)['pilot']
    reg.unlink(bound['id'])
    assert pilots.preview(reg)[0]['status'] == 'protected'
    pilots.apply(reg)
    assert 'pilot' not in active_sources(reg)


def test_ambiguous_or_different_address_is_not_bound(tmp_path):
    reg = registry(tmp_path)
    reg.update('pilot', name='风雅钱塘', aliases=[], address='另一个地址')
    assert pilots.preview(reg)[0]['status'] == 'unverified'
    pilots.apply(reg)
    assert 'pilot' not in active_sources(reg)
