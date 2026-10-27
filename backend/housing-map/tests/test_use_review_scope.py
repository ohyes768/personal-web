import pytest

from src.services.use_review_scope import auto_review_skip_reason


def row(**extra):
    return dict(district='滨江', address='月明路1076号', property_types=['公寓'],
                admission_state='excluded', sources=[], **extra)


@pytest.mark.parametrize('prop', ['写字楼', '商贸', '商铺', '厂房', '车位'])
def test_explicit_non_residential_uses_skip(prop):
    assert '非住宅' in auto_review_skip_reason({**row(), 'property_types': [prop]})


def test_other_means_unknown_use_and_must_not_skip_amap():
    assert auto_review_skip_reason({**row(), 'property_types': ['其他']}) is None


@pytest.mark.parametrize('props', [[], ['公寓'], ['商住两用'], ['住宅', '写字楼'], ['住宅', '其他']])
def test_unclear_and_conflicting_uses_are_kept(props):
    assert auto_review_skip_reason({**row(), 'property_types': props}) is None


def test_conflicting_or_missing_source_evidence_takes_priority_over_known_type():
    for qualification in ['type_missing', 'type_conflict']:
        assert auto_review_skip_reason({**row(), 'property_types': ['其他'],
                                        'qualification': qualification}) is None


def test_manual_decisions_are_skipped():
    assert '人工' in auto_review_skip_reason({**row(), 'admission': {
        'use_rule': 'use-review-v1', 'use_decision': 'residential'}})
    assert '人工' in auto_review_skip_reason({**row(), 'qualification': 'manual_exclusion'})


@pytest.mark.parametrize('state', ['pending', 'review', 'not_found', 'error'])
def test_admitted_residential_waits_for_completed_position(state):
    assert '定位' in auto_review_skip_reason({**row(), 'admission_state': 'admitted',
                                             'property_types': ['住宅'], 'position': {'state': state}})


@pytest.mark.parametrize('state', ['matched', 'manual'])
def test_positioned_residential_is_kept(state):
    assert auto_review_skip_reason({**row(), 'admission_state': 'admitted',
                                    'property_types': ['住宅'], 'position': {'state': state}}) is None


def test_region_anomaly_uses_address_evidence_not_the_project_name():
    assert '区域异常' in auto_review_skip_reason({**row(), 'address': '浙江省杭州市拱墅区艾润堂'})
    assert auto_review_skip_reason({**row(), 'community_name': '西湖区艺术园'}) is None
    assert auto_review_skip_reason({**row(), 'district': '萧山', 'address': '杭州市萧山区建设一路'}) is None
    assert auto_review_skip_reason({**row(), 'address': '杭州市滨江区拱墅路1号'}) is None


def test_source_address_conflict_and_manual_address_override():
    target = {**row(), 'sources': [{'source': 'tmsf', 'address': '杭州市拱墅区文晖路'}]}
    assert '区域异常' in auto_review_skip_reason(target)
    assert auto_review_skip_reason({**target, 'address_origin': 'manual'}) is None
