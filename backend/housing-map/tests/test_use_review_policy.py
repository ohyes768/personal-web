import pytest

from src.services.use_review_policy import (
    AGREE_NON_RESIDENTIAL, AGREE_RESIDENTIAL, CHECKED, CONFLICT, MIXED, NON_RESIDENTIAL,
    NOT_FOUND, PENDING_RETRY, RESIDENTIAL, UNCERTAIN, UNCERTAIN_RESULT,
    amap_category, compare, select_evidence, tmsf_category,
)


def poi(sid='B1', name='风雅钱塘', typecode='120302', type_text='住宅小区', adname='滨江区'):
    return dict(id=sid, name=name, adname=adname, address='月明路1076号',
                typecode=typecode, type=type_text, location='120.20749,30.20226')


def community(**extra):
    return {'community_id': 'c1', 'community_name': '风雅钱塘', 'aliases': [], 'district': '滨江区', **extra}


@pytest.mark.parametrize('typecode,expected', [
    ('120300', RESIDENTIAL), ('120301', RESIDENTIAL), ('120302', RESIDENTIAL),
    ('120303', RESIDENTIAL), ('120304', RESIDENTIAL),
    ('120302|120203', RESIDENTIAL), ('120302|120101', RESIDENTIAL),
    ('120203', MIXED), ('120203|120101', MIXED),
    ('120101', NON_RESIDENTIAL), ('120102', NON_RESIDENTIAL), ('010000', NON_RESIDENTIAL),
    ('', None), (None, None),
])
def test_amap_category_maps_typecodes(typecode, expected):
    assert amap_category(typecode) == expected


@pytest.mark.parametrize('types,expected', [
    ({'住宅'}, RESIDENTIAL), ({'别墅'}, RESIDENTIAL), ({'住宅', '别墅', '排屋'}, RESIDENTIAL),
    ({'商贸'}, NON_RESIDENTIAL), ({'写字楼'}, NON_RESIDENTIAL), ({'写字楼', '车位'}, NON_RESIDENTIAL),
    ({'住宅', '商贸'}, 'unknown'), ({'商住两用'}, 'unknown'), (set(), None),
])
def test_tmsf_category_classifies_type_sets(types, expected):
    assert tmsf_category(types) == expected


@pytest.mark.parametrize('types,amap,expected', [
    ({'住宅'}, RESIDENTIAL, AGREE_RESIDENTIAL),
    ({'别墅', '排屋'}, RESIDENTIAL, AGREE_RESIDENTIAL),
    ({'商贸'}, NON_RESIDENTIAL, AGREE_NON_RESIDENTIAL),
    ({'住宅'}, NON_RESIDENTIAL, CONFLICT),
    ({'商贸'}, RESIDENTIAL, CONFLICT),
    ({'住宅'}, MIXED, UNCERTAIN_RESULT),
    ({'商贸'}, MIXED, UNCERTAIN_RESULT),
    ({'住宅', '写字楼'}, RESIDENTIAL, UNCERTAIN_RESULT),
    ({'住宅'}, None, PENDING_RETRY),
])
def test_compare_follows_the_decision_matrix(types, amap, expected):
    assert compare(types, amap) == expected


def test_select_evidence_picks_the_named_residential_poi():
    result = select_evidence([poi()], community())
    assert result['state'] == CHECKED
    assert result['category'] == RESIDENTIAL
    assert result['candidates_count'] == 1
    assert result['evidence']['poi_id'] == 'B1'
    assert result['evidence']['name'] == '风雅钱塘'
    assert result['evidence']['typecode'] == '120302'
    assert result['evidence']['type_text'] == '住宅小区'
    assert result['evidence']['district'] == '滨江'
    assert result['evidence']['longitude'] == 120.20749
    assert result['evidence']['matched_by'] == 'exact'


def test_select_evidence_reports_a_named_non_residential_poi():
    result = select_evidence([poi(typecode='120101', type_text='写字楼')], community())
    assert result['state'] == CHECKED
    assert result['category'] == NON_RESIDENTIAL


def test_select_evidence_ignores_other_districts_and_unnamed_pois():
    rows = [poi(sid='B2', name='隔壁小区'), poi(sid='B3', adname='西湖区')]
    result = select_evidence(rows, community())
    assert result['state'] == NOT_FOUND
    assert result['category'] is None
    assert result['candidates_count'] == 0


def test_select_evidence_ignores_attached_places():
    rows = [poi(sid='B2', name='风雅钱塘小区出入口')]
    assert select_evidence(rows, community())['state'] == NOT_FOUND


def test_select_evidence_is_uncertain_when_candidates_disagree():
    rows = [poi(sid='B1'), poi(sid='B2', typecode='120101', type_text='写字楼')]
    result = select_evidence(rows, community())
    assert result['state'] == UNCERTAIN
    assert result['category'] is None
    assert result['candidates_count'] == 2


def test_select_evidence_keeps_one_category_when_candidates_agree():
    rows = [poi(sid='B1'), poi(sid='B2')]
    result = select_evidence(rows, community())
    assert result['state'] == CHECKED
    assert result['category'] == RESIDENTIAL
    assert result['candidates_count'] == 2
    assert result['evidence']['poi_id'] in {'B1', 'B2'}


def test_select_evidence_reports_how_the_name_matched():
    aliased = community(community_name='风雅钱塘世纪花园', aliases=['风雅钱塘'])
    assert select_evidence([poi(name='风雅钱塘')], aliased)['evidence']['matched_by'] == 'alias'
    loose = community(community_name='风雅钱塘世纪花园')
    result = select_evidence([poi(name='风雅钱塘世纪花园东区')], loose)
    assert result['evidence']['matched_by'] == 'loose'
