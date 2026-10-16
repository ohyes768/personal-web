from src.services.name_similarity import specialize, name_similarity


def test_identical_and_suffix_only_differences_bind_high():
    assert name_similarity('白金海岸', '白金海岸') >= 0.92
    # 通名差异不扣分：房天下"白金海岸花园"就是地图的"白金海岸"
    assert name_similarity('白金海岸花园', '白金海岸') >= 0.92
    assert name_similarity('白金海岸家园', '白金海岸') >= 0.92


def test_phase_mismatch_never_matches():
    # 字面极像但不是一家：一期/二期租金差几百，宁可人工也不自动绑
    assert name_similarity('白金海岸一期', '白金海岸二期') == 0.0
    assert name_similarity('白金海岸1期', '白金海岸二期') == 0.0


def test_homophone_names_score_via_pinyin():
    assert name_similarity('御峰花园', '御锋花园') >= 0.92


def test_developer_prefix_containment_scores_high():
    assert name_similarity('万科翡翠公园', '翡翠公园') >= 0.92


def test_unrelated_names_stay_low():
    assert name_similarity('白金海岸', '滨海花园') < 0.8
    assert name_similarity('白金海岸', '春江天玺') < 0.8


def test_specialize_strips_generic_but_keeps_digits():
    assert specialize('白金海岸花园') == '白金海岸'
    assert specialize('半岛小镇一期') == '半岛小镇一期'  # 无通名可剥，数字保留
