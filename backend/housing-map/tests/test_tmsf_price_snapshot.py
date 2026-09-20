from src.services.tmsf_fetcher import build_snapshots, parse_index_page


def test_index_parser_does_not_collect_recommended_listing_card_prices():
    index_html = """
    <span class="big">测试花园</span>
    <div class="house_guess"><text>52383元/㎡</text><text>40404元/㎡</text></div>
    """

    parsed = parse_index_page(index_html)

    assert "listing_unit_prices" not in parsed


def test_snapshot_builder_never_emits_visible_listing_card_average():
    index_html = """
    <span class="big">测试花园</span>
    <div class="house_guess"><text>52383元/㎡</text><text>40404元/㎡</text></div>
    """

    snapshots = build_snapshots("100", index_html, "")

    assert snapshots == []
