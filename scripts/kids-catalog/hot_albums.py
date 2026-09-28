"""Public 0-1-year-old album discovery; monthly snapshots, never audio downloads."""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

AGE_BAND = '0-1岁'
QT = 'https://m.qingting.fm/categories/1599/attrs/4394/'
XM = 'https://www.ximalaya.com/top/5/100092'
XM_EXPLICIT_INFANT_AGE = re.compile(r'(?:0\s*[-~～至到]\s*1\s*岁|0\s*岁\s*(?:\+|以上)|婴儿|婴幼儿)')
ROW_FIELDS = ('platform', 'album_id', 'title', 'url', 'plays', 'plays_value',
              'basis', 'source_url', 'source_rank', 'access', 'age_band',
              'age_evidence', 'age_confidence', 'candidate_rank')


def plays_number(value):
    match = re.fullmatch(r'([\d.]+)(万|亿)?', str(value).replace(',', '').strip())
    if not match:
        raise ValueError(f'无法识别播放量: {value}')
    return float(match[1]) * {'万': 10000, '亿': 100000000, None: 1}[match[2]]


def parse_qingting(html):
    soup = BeautifulSoup(html, 'html.parser')
    for script in soup.find_all('script'):
        text = script.string or script.get_text()
        match = re.search(r'window\.__initStores\s*=\s*', text)
        if not match:
            continue
        data = json.JSONDecoder().raw_decode(text[match.end():])[0]
        items = data.get('AttributeStore', {}).get('FilterList', [])
        rows = []
        for item in items:
            if item.get('category_id') != 1599:
                continue
            album_id = str(item['id'])
            if not album_id.isdigit() or not item.get('title'):
                continue
            plays = str(item.get('playcount', ''))
            rows.append(dict(platform='蜻蜓FM', album_id=album_id, title=item['title'],
                             url=f'https://m.qingting.fm/vchannels/{album_id}/',
                             plays=plays, plays_value=plays_number(plays),
                             basis='蜻蜓FM 0-1岁筛选页内按累计播放量排序',
                             source_url=QT, source_rank='', access='未核验',
                             age_band=AGE_BAND, age_evidence='蜻蜓FM年龄筛选',
                             age_confidence='高'))
        if rows:
            return rows
    raise ValueError('蜻蜓FM 0-1岁候选数据缺失，停止，不使用其他分类补齐')


def parse_ximalaya(html):
    soup = BeautifulSoup(html, 'html.parser')
    rows = []
    has_children_album = False
    for item in soup.select('.album-item'):
        category = item.select_one('.user-category_title')
        if not category or category.get_text(strip=True) != '儿童':
            continue
        has_children_album = True
        anchor = item.select_one('a[href]')
        title = item.select_one('.title')
        match = re.fullmatch(r'/album/(\d+)/?', anchor.get('href', '')) if anchor else None
        if not match or not title:
            continue
        description = item.select_one('.description')
        declared_text = ' '.join(filter(None, [title.get_text(' ', strip=True),
                                                description.get_text(' ', strip=True) if description else '']))
        if not XM_EXPLICIT_INFANT_AGE.search(declared_text):
            continue
        rank = item.select_one('.album-index')
        plays = item.select_one('.user-playcount')
        rows.append(dict(platform='喜马拉雅', album_id=match[1], title=title.get_text(strip=True),
                         url=f'https://www.ximalaya.com/album/{match[1]}',
                         plays=plays.get_text(strip=True) if plays else '', plays_value=None,
                         basis='儿童热播榜中简介明确标注婴儿年龄的作品', source_url=XM,
                         source_rank=rank.get_text(strip=True) if rank else '', access='未核验',
                         age_band=AGE_BAND, age_evidence='详情简介明确年龄标注',
                         age_confidence='中'))
    if not rows and not has_children_album:
        raise ValueError('喜马拉雅儿童榜缺失或被拦截，停止，不以全站榜补齐')
    return rows


def choose(rows, count, sort_plays=False, allow_short=False):
    unique = {(row['platform'], row['album_id']): row for row in reversed(rows)}
    rows = list(reversed(list(unique.values())))
    if sort_plays:
        rows.sort(key=lambda row: row['plays_value'], reverse=True)
    if len(rows) < count and not allow_short:
        raise ValueError(f'有效专辑不足: {len(rows)}/{count}，不生成完整榜单')
    return rows[:count]


def fetch_qingting():
    def read(url):
        with urlopen(Request(url, headers={'User-Agent': 'KidsCatalog/1.0'}), timeout=30) as response:
            return response.read().decode('utf-8')

    robot = RobotFileParser()
    robot.parse(read('https://m.qingting.fm/robots.txt').splitlines())
    if not robot.can_fetch('KidsCatalog', QT):
        raise RuntimeError('蜻蜓FM robots 不允许此目录，停止')
    return parse_qingting(read(QT))


def fetch_ximalaya():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(service_workers='block')
            page = context.new_page()
            blocked = []

            def guard(route):
                request = route.request
                if (request.resource_type == 'media' or '/revision/play/' in request.url
                        or urlsplit(request.url).hostname in ('localhost', '127.0.0.1', '::1')):
                    route.abort()
                else:
                    route.continue_()

            def observe(response):
                host = urlsplit(response.url).hostname or ''
                if host.endswith('ximalaya.com') and response.status in (403, 429):
                    blocked.append(f'HTTP {response.status}')

            page.route('**/*', guard)
            page.on('response', observe)
            response = page.goto(XM, wait_until='domcontentloaded', timeout=45000)
            if not response or response.status != 200:
                raise RuntimeError('喜马拉雅榜单响应异常')
            page.wait_for_selector('.album-item .title', timeout=20000)
            if blocked:
                raise RuntimeError('喜马拉雅限制访问: ' + ', '.join(blocked))
            return parse_ximalaya(page.content())
        finally:
            browser.close()


def report(snapshot):
    lines = [f"# {snapshot['month']} 0–1岁专辑候选（{snapshot['actual_count']}个）", '',
             f"采集时间：{snapshot['collected_at']}", '',
             '仅接受蜻蜓FM的0–1岁筛选，或喜马拉雅简介明确的婴儿年龄标注；数量不足时不补充普通儿童内容。免费采集不代表音频免费。', '',
             '| 平台 | 序号 | 专辑 | 年龄依据 |', '|---|---:|---|---|']
    for row in snapshot['albums']:
        title = row['title'].replace('|', '／').replace('\n', ' ')
        lines.append(f"| {row['platform']} | {row['candidate_rank']} | [{title}]({row['url']}) | {row['age_evidence']}（{row['age_confidence']}） |")
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent / 'data' / 'hot-albums')
    args = parser.parse_args()
    now = datetime.now(timezone(timedelta(hours=8)))
    month = now.strftime('%Y-%m')
    snapshot_name = f'{month}-0-1'
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / f'{snapshot_name}.json'
    lock = args.output_dir / f'.{snapshot_name}.collect.lock'

    if path.exists():
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        if any(row.get('age_band') != AGE_BAND for row in snapshot['albums']):
            raise ValueError('缓存年龄段不匹配，请检查缓存文件')
    else:
        with lock.open('x', encoding='utf-8') as handle:
            handle.write(now.isoformat())
        try:
            attempt = args.output_dir / f'{snapshot_name}.attempt'
            if attempt.exists():
                raise RuntimeError(f'本月已有失败采集；排查后手动删除 {attempt} 再运行')
            attempt.write_text(now.isoformat(), encoding='utf-8')
            qingting_rows = choose(fetch_qingting(), 15, sort_plays=True, allow_short=True)
            ximalaya_rows = choose(fetch_ximalaya(), 15, allow_short=True)
            for platform_rows in (qingting_rows, ximalaya_rows):
                for index, row in enumerate(platform_rows, start=1):
                    row['candidate_rank'] = index
            rows = qingting_rows + ximalaya_rows
            snapshot = dict(month=month, age_band=AGE_BAND, requested_count=30,
                            actual_count=len(rows), collected_at=now.isoformat(), albums=rows)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(path)
            attempt.unlink()
        finally:
            lock.unlink()

    markdown = report(snapshot)
    path.with_suffix('.md').write_text(markdown, encoding='utf-8')
    with path.with_suffix('.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(snapshot['albums'])
    print(markdown)
    print(f'已保存 JSON / CSV / Markdown：{path.parent}', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'采集失败：{error}', file=sys.stderr)
        sys.exit(1)