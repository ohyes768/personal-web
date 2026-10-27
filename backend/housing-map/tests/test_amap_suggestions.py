import pytest

from src.services.directory_use_review import _search_review


@pytest.mark.parametrize('suggestion_id', [None, '', []])
def test_zero_count_geocoding_suggestion_is_complete_empty(suggestion_id):
    class Client:
        def search_name(self, *args, **kwargs):
            return [dict(id=suggestion_id, name='浙江省杭州市余杭区西园', location='120,30')], 0
    assert _search_review(Client(), '广润西园', '滨江', cancelled=lambda: False) == ([], True)


def test_positive_count_missing_identity_stays_incomplete():
    class Client:
        def search_name(self, *args, **kwargs):
            return [dict(name='建议地址')], 1
    assert _search_review(Client(), '测试', '滨江', cancelled=lambda: False) == ([], False)


def test_zero_count_real_identity_is_not_treated_as_address_suggestion():
    class Client:
        def search_name(self, *args, **kwargs):
            return [dict(id='P1', name='真实地点')], 0
    rows, complete = _search_review(Client(), '测试', '滨江', cancelled=lambda: False)
    assert rows == [dict(id='P1', name='真实地点')]
    assert not complete
