"""Low-frequency collection of Fang's public Hangzhou rental listings.

Records are asking rents, not leases. No existing housing price data is written.
"""
from __future__ import annotations

import datetime as dt
import html as html_module
import json
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from src.services.tmsf_fetcher import DEFAULT_HEADERS, decode_response_bytes, strip_tags

BASE_URL = 'https://zu.fang.com'
CHALLENGE_HOST = 'check.3g.fang.com'
CHALLENGE_PAUSE_SEEDS = 2
CHALLENGE_PAUSE_MESSAGE = '房天下要求滑块验证（IP 被风控），本轮暂停剩余来源采集，稍后重试'


class FangChallenge(ValueError):
    """Fang redirected to its slider challenge (check.3g.fang.com): IP-level risk control."""


def ignored_community(sid):
    if not sid:
        return False
    from src.services.data_loader import DATA_DIR
    from src.services.community_registry import existing_registry
    registry = existing_registry(DATA_DIR)
    return bool(registry and registry.is_ignored('fang', 'community', sid))


def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in {'zu.fang.com', 'hz.zu.fang.com'}
            or parts.username or parts.password or parts.port not in {None, 443}
            or not re.fullmatch(r'/(?:hz/)?(?:house[^/]*|chuzu)(?:/[^?#]*)?', parts.path)):
        raise ValueError('Only HTTPS Hangzhou Fang rental list/detail URLs are supported')
    if parts.hostname == 'zu.fang.com' and not parts.path.startswith('/hz/'):
        raise ValueError('Only Hangzhou rental URLs are supported')
    return url


def _links(html: str) -> list[tuple[str, str]]:
    return [(html_module.unescape(href), strip_tags(label)) for href, label in re.findall(
        r'<a\b[^>]*href=["\x27]([^"\x27]+)["\x27][^>]*>(.*?)</a>', html, re.I | re.S)]


def parse_listing_page(html: str, url: str) -> tuple[list[dict], str | None]:
    validate_url(url)
    rows = []
    for block in re.findall(r'<dl\b[^>]*>(.*?)</dl>', html, re.I | re.S):
        links = _links(block)
        detail = [(href, label) for href, label in links
                  if re.search(r'/chuzu/\d+_\d+_\d+\.htm', href)]
        if not detail:
            continue
        text = strip_tags(block)
        # A listing occasionally anchors a non-rental destination (e.g. an ad slot
        # or a detail link that has been moved off `zu.fang.com/hz/...`). Skip
        # such rows instead of failing the whole page.
        try:
            source_url = validate_url(urljoin(url, detail[0][0]))
            listing_id = re.search(r'/chuzu/(\d+_\d+_\d+)\.htm', source_url).group(1)
        except ValueError:
            continue
        title = next((label for _, label in detail if label and label != '图片'), '')
        community = next(((href, label) for href, label in links
                          if re.search(r'/house-xm\d+', href) and label), None)
        rent = re.search(r'([\d,]+(?:\.\d+)?)\s*元/月', text)
        paragraphs = [strip_tags(p) for p in re.findall(r'<p\b[^>]*>(.*?)</p>', block, re.I | re.S)]
        info = next((p for p in paragraphs if '|' in p and re.search(r'整租|合租', p)), '')
        area = re.search(r'(\d+(?:\.\d+)?)\s*(?:㎡|平米|平方米)', info)
        layout = re.search(r'\d+室(?:\d+厅)?(?:\d+卫)?|\d+户合租', info)
        mode = 'shared' if '合租' in text else 'whole' if '整租' in text else 'unknown'
        flags = []
        if mode == 'shared':
            flags.append('shared_rental')
        if mode == 'unknown':
            flags.append('unknown_rental_mode')
        if re.search(r'独立厨卫|隔断|分割|单间|主卧|次卧', title):
            flags.append('suspected_partition')
        if not community:
            flags.append('missing_community')
        if not rent or not area:
            flags.append('missing_price_or_area')
        if (rent and float(rent.group(1).replace(',', '')) <= 0) or (area and float(area.group(1)) <= 0):
            flags.append('invalid_price_or_area')
        rows.append({
            'source': 'fang', 'source_listing_id': listing_id, 'source_url': source_url,
            'source_community_id': re.search(r'house-xm(\d+)', community[0]).group(1) if community else None,
            'community_name': community[1] if community else None, 'title': title,
            'monthly_rent_yuan': float(rent.group(1).replace(',', '')) if rent else None,
            'area_m2': float(area.group(1)) if area else None,
            'layout': layout.group(0) if layout else None, 'rental_mode': mode,
            'price_kind': 'listing_rent', 'published_at': None,
            'address': None, 'property_type': None, 'quality_flags': flags,
        })
    next_url = next((urljoin(url, href) for href, label in _links(html) if label == '下一页'), None)
    if next_url:
        try:
            validate_url(next_url)
        except ValueError:
            # Pagination anchor doesn't reach a recognized rental list — stop
            # following pages instead of failing the whole batch. Details on
            # the current page were already captured above.
            next_url = None
        else:
            if '/chuzu/' in next_url:
                raise ValueError('Unexpected detail URL in pagination')
    if not rows:
        text = strip_tags(html)
        if not ('房天下' in text and re.search(r'暂无房源|没有找到|0\s*套|未找到', text)):
            raise ValueError('Unrecognized rental page (login, challenge or changed HTML)')
    return rows, next_url


def enrich_detail(row: dict, html: str) -> None:
    text = strip_tags(html)
    if '房天下' not in text or not re.search(r'出租方式|费用明细', text):
        raise ValueError('Unrecognized rental detail page')
    prop = re.search(r'物业类型\s+(\S+)', text)
    address = re.search(r'地\s*址\s+(.+?)(?:电话咨询|微信扫码|地图|周边配套|房源信息)', text)
    row['property_type'] = prop.group(1) if prop else None
    row['address'] = address.group(1).strip() if address else None
    if row['property_type'] and row['property_type'] not in {'住宅', '普通住宅'}:
        row['quality_flags'].append('non_residential')
    row['detail_fetched'] = True


class FangClient:
    def __init__(self, timeout: int = 20):
        from curl_cffi import requests
        self.session = requests.Session(impersonate='chrome')
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        validate_url(url)
        # Redirects are followed explicitly so unexpected destinations are never requested.
        for _ in range(4):
            response = self.session.get(url, headers=DEFAULT_HEADERS,
                                        timeout=self.timeout, allow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308}:
                target = urljoin(url, response.headers['Location'])
                if urlsplit(target).hostname == CHALLENGE_HOST:
                    # Slider challenge: the IP is risk-controlled; retrying just
                    # burns requests, so fail with an explicit human-readable cause.
                    raise FangChallenge('房天下要求滑块验证（IP 被风控），请稍后重试')
                url = validate_url(target)
                continue
            response.raise_for_status()
            return decode_response_bytes(response.content, response.encoding)
        raise ValueError('Too many redirects')

    def close(self) -> None:
        self.session.close()


def crawl(seeds: list[str], *, fetch: Callable[[str], str], max_pages: int = 3,
          delay: float = 2, details: bool = False) -> tuple[list[dict], dict]:
    if max_pages < 1 or delay < 0:
        raise ValueError('max_pages must be positive and delay nonnegative')
    captured_at = dt.datetime.now(dt.UTC).isoformat()
    report = {'captured_at': captured_at, 'pages_succeeded': 0, 'duplicate_ids': 0,
              'errors': [], 'truncated_seeds': [], 'seeds': seeds, 'ignored': 0}
    records: dict[str, dict] = {}
    visited = set()
    requests_made = 0

    def request(url: str) -> str:
        nonlocal requests_made
        if requests_made:
            time.sleep(delay)
        requests_made += 1
        return fetch(url)

    for seed in seeds:
        seed_id = re.search(r'house-xm(\d+)', seed)
        if seed_id and ignored_community(seed_id[1]):
            report['ignored'] += 1
            continue
        url = seed
        for _ in range(max_pages):
            if url in visited:
                break
            visited.add(url)
            try:
                rows, next_url = parse_listing_page(request(validate_url(url)), url)
                report['pages_succeeded'] += 1
            except Exception as error:
                report['errors'].append({'url': url, 'stage': 'list', 'error': str(error)})
                break
            for row in rows:
                if ignored_community(row.get('source_community_id')):
                    report['ignored'] += 1
                    continue
                key = row['source_listing_id']
                if key in records:
                    report['duplicate_ids'] += 1
                    continue
                row['captured_at'] = captured_at
                if details:
                    try:
                        enrich_detail(row, request(row['source_url']))
                    except Exception as error:
                        row['quality_flags'].append('detail_fetch_failed')
                        report['errors'].append({'url': row['source_url'], 'stage': 'detail', 'error': str(error)})
                records[key] = row
            if not next_url:
                break
            url = next_url
        else:
            if url not in visited:
                report['truncated_seeds'].append(seed)
    report['requests_made'] = requests_made
    report['listing_count'] = len(records)
    return list(records.values()), report


@dataclass
class SeedRunResult:
    """Per-seed crawl outcome: one community seed with a completeness status.

    status is one of complete / truncated / list_failed / partial_detail /
    empty_ok (empty listing page = success with zero samples). Samples of
    failed seeds are kept for diagnostics only; callers must not publish them.
    """
    seed: str
    samples: list[dict] = field(default_factory=list)
    pages_fetched: int = 0
    pages_truncated: bool = False
    detail_success: int = 0
    detail_failed: int = 0
    duplicate_ids: int = 0
    status: str = 'complete'
    errors: list[dict] = field(default_factory=list)


class RentalCrawlCancelled(Exception):
    """cancel_event fired mid-crawl; completed and partial work stays usable for reporting."""

    def __init__(self, completed: list[SeedRunResult], partial: SeedRunResult | None):
        super().__init__('rental crawl cancelled')
        self.completed = completed
        self.partial = partial


class CrawlProgress:
    """Read-only counters for a running crawl; page/detail counts are auxiliary, never a percent."""

    def __init__(self, total_seeds: int):
        self.total_seeds = total_seeds
        self.processed_seeds = 0
        self.current_seed: str | None = None
        self.pages_fetched = 0
        self.details_fetched = 0

    def snapshot(self) -> dict:
        return {'total_seeds': self.total_seeds, 'processed_seeds': self.processed_seeds,
                'current_seed': self.current_seed, 'pages_fetched': self.pages_fetched,
                'details_fetched': self.details_fetched}


def crawl_runs(seeds: list[str], *, fetch: Callable[[str], str], max_pages: int = 3,
               delay: float = 2, details: bool = False,
               cancel_event: threading.Event | None = None,
               progress: CrawlProgress | None = None,
               skip_seed: Callable[[str], bool] | None = None) -> Iterator[SeedRunResult]:
    """Crawl seed by seed, yielding one SeedRunResult per seed.

    Cancellation is checked before every request and inside every delay wait
    (cancel_event.wait, so an external set() wakes it immediately); a cancel
    raises RentalCrawlCancelled keeping already fetched samples and completed
    seeds. Dedup by source listing ID stays global across seeds.
    """
    if max_pages < 1 or delay < 0:
        raise ValueError('max_pages must be positive and delay nonnegative')
    captured_at = dt.datetime.now(dt.UTC).isoformat()
    seen_ids: set[str] = set()
    visited: set[str] = set()
    requests_made = 0
    challenge_streak = 0
    completed: list[SeedRunResult] = []

    def cancelled(partial: SeedRunResult | None) -> RentalCrawlCancelled:
        return RentalCrawlCancelled(list(completed), partial)

    def request(url: str, partial: SeedRunResult | None) -> str:
        nonlocal requests_made
        if cancel_event is not None:
            if cancel_event.is_set():
                raise cancelled(partial)
            if requests_made and cancel_event.wait(delay):
                raise cancelled(partial)
        elif requests_made:
            time.sleep(delay)
        requests_made += 1
        return fetch(url)

    for seed in seeds:
        if progress is not None:
            progress.current_seed = seed
        result = SeedRunResult(seed=seed)
        if skip_seed and skip_seed(seed):
            result.status = 'list_failed'
            result.errors.append({'url': seed, 'stage': 'directory', 'error': '来源已删除或关联已改变，跳过采集'})
            if progress is not None:
                progress.processed_seeds += 1
            yield result
            continue
        if challenge_streak >= CHALLENGE_PAUSE_SEEDS:
            # Consecutive seeds all hit the slider challenge: remaining seeds
            # would only repeat it, so pause them without another request.
            result.status = 'list_failed'
            result.errors.append({'url': seed, 'stage': 'list', 'error': CHALLENGE_PAUSE_MESSAGE})
            if progress is not None:
                progress.processed_seeds += 1
                progress.current_seed = None
            yield result
            continue
        url = seed
        raw_rows = 0
        list_failed = False
        challenge_hit = False
        for _ in range(max_pages):
            if url in visited:
                break
            visited.add(url)
            try:
                rows, next_url = parse_listing_page(request(validate_url(url), result), url)
            except RentalCrawlCancelled:
                raise
            except FangChallenge as error:
                challenge_hit = True
                result.errors.append({'url': url, 'stage': 'list', 'error': str(error)})
                list_failed = True
                break
            except Exception as error:
                result.errors.append({'url': url, 'stage': 'list', 'error': str(error)})
                list_failed = True
                break
            result.pages_fetched += 1
            if progress is not None:
                progress.pages_fetched += 1
            raw_rows += len(rows)
            for row in rows:
                key = row['source_listing_id']
                if key in seen_ids:
                    result.duplicate_ids += 1
                    continue
                seen_ids.add(key)
                row['captured_at'] = captured_at
                if skip_seed and skip_seed(seed):
                    continue
                if details:
                    try:
                        enrich_detail(row, request(row['source_url'], result))
                        result.detail_success += 1
                        if progress is not None:
                            progress.details_fetched += 1
                    except RentalCrawlCancelled:
                        raise
                    except Exception as error:
                        row['quality_flags'].append('detail_fetch_failed')
                        result.detail_failed += 1
                        result.errors.append({'url': row['source_url'], 'stage': 'detail', 'error': str(error)})
                result.samples.append(row)
            if not next_url:
                break
            url = next_url
        else:
            if url not in visited:
                result.pages_truncated = True
        if list_failed:
            result.status = 'list_failed'
        elif result.pages_truncated:
            result.status = 'truncated'
        elif result.detail_failed:
            result.status = 'partial_detail'
        elif raw_rows == 0:
            result.status = 'empty_ok'
        challenge_streak = challenge_streak + 1 if challenge_hit else 0
        completed.append(result)
        if progress is not None:
            progress.processed_seeds += 1
            progress.current_seed = None
        yield result


def write_run(rows: list[dict], report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {'fang_rentals.jsonl': ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows),
               'fang_rentals_report.json': json.dumps(report, ensure_ascii=False, indent=2) + '\n'}
    for name, content in outputs.items():
        path = output_dir / name
        temp = path.with_suffix(path.suffix + '.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(path)
