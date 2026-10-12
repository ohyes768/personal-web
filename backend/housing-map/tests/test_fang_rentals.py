import json
import pytest
from src.services.fang_rentals import crawl, enrich_detail, parse_listing_page, validate_url, write_run

URL = 'https://zu.fang.com/hz/house-xm2010067741/'

def page(rows, next_link=''):
    return '<title>杭州租房 - 房天下</title><div class="houseList">' + rows + '</div>' + next_link

def listing(id='3_123_1', mode='整租', title='三房出租'):
    return f'''<dl><dt><a href="/hz/chuzu/{id}.htm">图片</a></dt><dd>
    <p class="title"><a href="/hz/chuzu/{id}.htm">{title}</a></p>
    <p class="font15">{mode} | 3室2厅 | 89㎡ | 朝南</p>
    <p><a>滨江</a>-<a>长河</a>-<a href="/hz/house-xm2010067741/">风雅钱塘</a></p>
    <div class="moreInfo"><p><b>6,400</b> 元/月</p></div></dd></dl>'''

def test_parse_structured_community_price_and_flags():
    rows, _ = parse_listing_page(page(listing(title='东方郡风雅钱塘独立厨卫')), URL)
    assert rows[0]['community_name'] == '风雅钱塘'
    assert rows[0]['source_community_id'] == '2010067741'
    assert rows[0]['monthly_rent_yuan'] == 6400
    assert rows[0]['area_m2'] == 89
    assert rows[0]['published_at'] is None
    assert 'suspected_partition' in rows[0]['quality_flags']
    rows, _ = parse_listing_page(page(listing(mode='合租主卧')), URL)
    assert rows[0]['rental_mode'] == 'shared'
    assert 'shared_rental' in rows[0]['quality_flags']

@pytest.mark.parametrize('html', ['<title>登录</title>', '<html>验证您的身份</html>', '<title>房天下</title><p>广告</p>'])
def test_unrecognized_pages_are_errors(html):
    with pytest.raises(ValueError):
        parse_listing_page(html, URL)

def test_pagination_dedup_and_partial_error():
    first = page(listing(), '<a href="/hz/house-xm2010067741/i32/">下一页</a>')
    pages = {URL: first, 'https://zu.fang.com/hz/house-xm2010067741/i32/': page(listing() + listing('1_456_1'))}
    rows, report = crawl([URL, 'https://zu.fang.com/hz/house-xm999/'], fetch=lambda u: pages[u], delay=0)
    assert len(rows) == 2
    assert report['duplicate_ids'] == 1
    assert len(report['errors']) == 1
    assert report['pages_succeeded'] == 2

def test_empty_page_and_pagination_limit():
    rows, report = crawl([URL], fetch=lambda u: page('', '<p>暂无房源</p>'), delay=0)
    assert rows == [] and not report['errors']
    rows, report = crawl([URL], fetch=lambda u: page(listing(), '<a href="/hz/house-xm2010067741/i32/">下一页</a>'), max_pages=1, delay=0)
    assert report['truncated_seeds'] == [URL]

def test_write_independent_outputs(tmp_path):
    rows, report = crawl([URL], fetch=lambda u: page(listing()), delay=0)
    write_run(rows, report, tmp_path)
    saved = json.loads((tmp_path / 'fang_rentals.jsonl').read_text(encoding='utf-8'))
    assert saved['price_kind'] == 'listing_rent'
    assert saved['captured_at']
    assert json.loads((tmp_path / 'fang_rentals_report.json').read_text(encoding='utf-8'))['listing_count'] == 1

def test_structured_layout_wins_over_title():
    rows, _ = parse_listing_page(page(listing(title='3室房东直租')), URL)
    assert rows[0]['layout'] == '3室2厅'

def test_detail_and_partial_failure():
    rows, _ = parse_listing_page(page(listing()), URL)
    enrich_detail(rows[0], '<title>房天下</title>费用明细 物业类型 商业公寓 地 址 月明路1076号 电话咨询')
    assert rows[0]['address'] == '月明路1076号'
    assert 'non_residential' in rows[0]['quality_flags']
    rows, report = crawl([URL], fetch=lambda u: page(listing()) if u == URL else '<title>登录</title>', delay=0, details=True)
    assert len(rows) == 1
    assert 'detail_fetch_failed' in rows[0]['quality_flags']
    assert report['errors'][0]['stage'] == 'detail'

@pytest.mark.parametrize('url', ['https://example.com/hz/house/', 'http://zu.fang.com/hz/house/', 'https://zu.fang.com/sh/house/', 'https://zu.fang.com@evil.com/hz/house/'])
def test_only_expected_public_rental_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)
