import pytest

from src.services.directory_policy import eligibility
from src.services.use_review_policy import RULE_VERSION, use_identity


def community(**extra):
    return {'community_id': 'c1', 'community_name': '风雅钱塘', 'aliases': [], 'district': '滨江区', **extra}


def tmsf(property_type='商贸', **extra):
    record = {'source': 'tmsf', 'source_id': 't1', 'name': '风雅钱塘', 'district': '滨江',
              'address': '月明路1076号', 'property_type': property_type, 'listing_count': 3,
              'market_state': 'second_hand'}
    record.update(extra)
    return record


def review(state='checked', category='residential', checked_at='2026-10-23T00:00:00+00:00', **extra):
    return {'use_review': {'identity': use_identity(community()), 'rule_version': RULE_VERSION, 'state': state,
                            'category': category, 'checked_at': checked_at, 'evidence': {}, **extra}}


def admission(**extra):
    return {'state': 'excluded', 'decision_kind': 'manual', 'revision': 1, 'auto_review_locked': False, **extra}


def test_without_review_evidence_the_current_verdict_is_unchanged():
    assert eligibility(community(), [tmsf('住宅')])['qualification'] == 'eligible'
    assert eligibility(community(), [tmsf('商贸')])['qualification'] == 'non_residential'
    assert eligibility(community(), [tmsf('商贸')])['exclusion_reason'] == '透明售房网用途为商贸，不收录'
    assert eligibility(community(), [tmsf(property_type=None)])['qualification'] == 'type_missing'
    assert eligibility(community(), [tmsf('住宅', property_type_conflict=True)])['qualification'] == 'type_conflict'
    assert eligibility(community(), [tmsf(property_type='商住两用')])['qualification'] == 'type_uncertain'


def test_a_missing_or_failed_review_keeps_the_current_verdict():
    for state in ('not_found', 'error', 'uncertain', None):
        c = community(**review(state=state))
        assert eligibility(c, [tmsf('商贸')])['qualification'] == 'non_residential'
        assert eligibility(c, [tmsf('住宅')])['qualification'] == 'eligible'


def test_agreeing_evidence_keeps_the_current_verdict():
    c = community(**review(category='residential'))
    assert eligibility(c, [tmsf('住宅')])['qualification'] == 'eligible'
    c = community(**review(category='non_residential'))
    assert eligibility(c, [tmsf('商贸')])['qualification'] == 'non_residential'


def test_a_conflict_becomes_pending_review_instead_of_exclusion():
    c = community(**review(category='residential'))
    result = eligibility(c, [tmsf('商贸')])
    assert result['qualification'] == 'use_conflict'
    assert result['admission_state'] == 'excluded'
    assert result['facts_state'] == 'incomplete'
    c = community(**review(category='non_residential'))
    result = eligibility(c, [tmsf('住宅')])
    assert result['qualification'] == 'use_conflict'
    assert result['facts_state'] == 'incomplete'


def test_mixed_or_unknown_classifications_become_pending_review():
    c = community(**review(category='mixed'))
    assert eligibility(c, [tmsf('住宅')])['qualification'] == 'use_uncertain'
    c = community(**review(category='residential'))
    assert eligibility(c, [tmsf(property_type='商住两用')])['qualification'] == 'use_uncertain'


def test_a_human_residential_decision_passes_the_use_gate():
    c = community(**review(category='residential'))
    confirmed = admission(state='admitted', use_rule=RULE_VERSION, use_decision='residential',
                          property_type='住宅', decided_at='2026-10-23T00:00:00+00:00')
    result = eligibility(c, [tmsf('商贸')], {}, confirmed)
    assert result['qualification'] == 'eligible'
    assert result['effective_property_type'] == '住宅'


def test_a_human_decision_still_respects_the_other_gates():
    c = community(address='', address_origin='manual')
    confirmed = admission(state='admitted', use_rule=RULE_VERSION, use_decision='residential',
                          property_type='住宅', decided_at='2026-10-23T00:00:00+00:00')
    result = eligibility(c, [tmsf('商贸', address='')], {}, confirmed)
    assert result['qualification'] == 'address_missing'


def test_a_human_non_residential_decision_excludes_with_its_reason():
    c = community(**review(category='residential'))
    confirmed = admission(state='excluded', use_rule=RULE_VERSION, use_decision='non_residential',
                          reason='克而瑞与高德均为写字楼', decided_at='2026-10-23T00:00:00+00:00')
    result = eligibility(c, [tmsf('住宅')], {}, confirmed)
    assert result['qualification'] == 'manual_exclusion'
    assert result['exclusion_reason'] == '克而瑞与高德均为写字楼'


def test_new_contrary_evidence_sends_the_decision_back_to_review():
    c = community(**review(category='non_residential', checked_at='2026-10-24T00:00:00+00:00'))
    confirmed = admission(state='admitted', use_rule=RULE_VERSION, use_decision='residential',
                          property_type='住宅', decided_at='2026-10-23T00:00:00+00:00')
    result = eligibility(c, [tmsf('商贸')], {}, confirmed)
    assert result['qualification'] == 'use_conflict'
    assert result['facts_state'] == 'incomplete'


def test_an_older_review_does_not_undo_a_human_decision():
    c = community(**review(category='non_residential', checked_at='2026-10-22T00:00:00+00:00'))
    confirmed = admission(state='admitted', use_rule=RULE_VERSION, use_decision='residential',
                          property_type='住宅', decided_at='2026-10-23T00:00:00+00:00')
    assert eligibility(c, [tmsf('商贸')], {}, confirmed)['qualification'] == 'eligible'


def test_a_plain_manual_exclusion_is_not_affected_by_review_evidence():
    c = community(**review(category='residential'))
    excluded = admission(state='excluded', decision_kind='manual', auto_review_locked=True, reason='人工排除')
    result = eligibility(c, [tmsf('商贸')], {}, excluded)
    assert result['qualification'] == 'manual_exclusion'
    assert result['exclusion_reason'] == '人工排除'
