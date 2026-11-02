"""An occupied rental source identifies its current owner without rebinding."""
import pytest

from src.services.community_registry import CommunityRegistry
from src.services.rental_reference.xingfuli_sources import bind_source, _human_veto


def test_occupied_source_names_existing_owner_and_keeps_association(tmp_path):
    registry = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    owner = registry.create('国信嘉园', community_id='10001508', district='滨江')
    target = registry.create('国信嘉园(排屋）', community_id='20153704', district='滨江')
    candidate = dict(neighborhood_id='6581009437522133255', name='国信嘉园', address='滨盛路4050号',
                     coordinate_system='gcj02', longitude=120.161703, latitude=30.189708)
    rid = bind_source(registry, owner, candidate, seed='7419094309133140020')
    with pytest.raises(ValueError) as error:
        bind_source(registry, target, candidate, seed='7419094309133140020')
    assert str(error.value) == '该幸福里来源已关联：国信嘉园（小区ID：10001508），请先核对'
    source = next(s for s in registry.sources() if s['id'] == rid)
    assert source['community_id'] == owner['community_id']


def test_missing_owner_still_identifies_the_record_to_check(tmp_path):
    registry = CommunityRegistry(tmp_path/'community_registry.sqlite3')
    target = registry.create('排屋', community_id='target')
    message = _human_veto(registry, target['community_id'], dict(
        id='source', community_id='missing-owner', status='matched'))
    assert '名称未知' in message and 'missing-owner' in message
