"""The pending table reads saved evidence and never triggers discovery."""
from tests.test_rental_probe import setup, homepage, TOTAL_ID, PHASE_ID
from src.services.rental_reference.probe import write_state, read_state, STAGE_NEEDS_SELECTION
from src.services.rental_reference.matching import source_reviews, selection_summary


def test_review_list_exposes_current_candidate_names_counts_and_address(tmp_path):
    registry = setup(tmp_path, name='保亿风景蝶院')
    candidates = [{**homepage(neighborhood_id=nid, name=f'保亿风景蝶院({scope})'),
                   'candidate_id': 'second_hand:'+nid, 'conflicts': ['旧版分期冲突']}
                  for nid, scope in [(TOTAL_ID, '留园'), (PHASE_ID, '观园')]]
    write_state(registry, 'c1', stage=STAGE_NEEDS_SELECTION, message='请选择对应的小区主页', candidates=candidates)
    before = read_state(registry, 'c1')
    row = source_reviews(registry)[0]
    assert row['candidate_count'] == row['selectable_count'] == 2
    assert [c['name'] for c in row['candidates']] == ['保亿风景蝶院(留园)', '保亿风景蝶院(观园)']
    assert row['address'] == '测试路1号'
    assert '分园' in row['selection_reason']
    assert read_state(registry, 'c1') == before


def test_all_unselectable_candidates_show_actual_conflict():
    c = dict(community_name='锦绣江南', district='滨江')
    state = dict(candidates=[{**homepage(name='锦绣江南'), 'district': '桐庐'}])
    summary = selection_summary(c, state)
    assert summary['candidate_count'] == 1 and summary['selectable_count'] == 0
    assert '桐庐' in summary['selection_reason']


def test_specific_search_reason_is_kept_and_empty_legacy_candidates_are_honest():
    c = dict(community_name='测试花园', district='滨江')
    message = '搜索分页返回重复房源，无法确认唯一候选，请核对小区主页'
    summary = selection_summary(c, dict(candidates=[homepage()], message=message))
    assert summary['selection_reason'] == message
    empty = selection_summary(c, {})
    assert empty['candidate_count'] == empty['selectable_count'] == 0
    assert '重新探查' in empty['selection_reason']
