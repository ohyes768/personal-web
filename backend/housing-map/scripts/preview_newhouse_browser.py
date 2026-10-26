"""Read-only production evidence preview; never writes sources or admission decisions."""
import argparse
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import closing, contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services.community_address import valid_address
from src.services.community_registry import CommunityRegistry, now
from src.services.residential_classifier import classify_sources
from src.services.tmsf_fetcher import TmsfClient
from src.services.tmsf_property_type import fetch_project_facts_by_id


class PreviewRegistry(CommunityRegistry):
    """Close every scratch connection before removing the snapshot on Windows."""
    @contextmanager
    def db(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            with db:
                yield db


def preview(registry, *, limit=3, names=None, client=None):
    # mode=ro + backup into disposable storage. Even helper BEGIN IMMEDIATE calls
    # can only target the copy; the production registry is never constructed here.
    if Path.cwd().resolve().is_relative_to(Path(registry).resolve().parent):
        raise ValueError('请从生产数据目录之外运行预览，避免在数据目录创建临时文件')
    with tempfile.TemporaryDirectory(prefix='.newhouse-preview-', dir=Path.cwd()) as temporary:
        snapshot = Path(temporary) / 'registry.sqlite3'
        with closing(sqlite3.connect(Path(registry).resolve().as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(snapshot)) as copy:
                source.backup(copy)
        store = PreviewRegistry(snapshot)
        projects = [r for r in store.sources() if r['source'] == 'tmsf' and
                    r.get('source_kind') == 'project' and r['status'] != 'ignored' and
                    (not names or r['name'] in names)]
        rows = []
        owned = client is None
        client = client or TmsfClient()
        try:
            for record in projects[:limit]:
                row = dict(name=record['name'], source_id=record['source_id'],
                           existing_community_id=record.get('community_id'))
                try:
                    facts = fetch_project_facts_by_id(client, siteid=record.get('project_siteid'),
                        propertyid=record.get('project_id'), names=[record['name'], *record.get('aliases', [])],
                        district=record.get('district'), previous=record)
                    row['facts'] = {k: v for k, v in facts.items() if k != 'newhouse_detail_cache'}
                    merged = {**record, **facts}
                    category = classify_sources([merged], {})
                    row['category'] = ('non_residential' if category == 'non_residential' or facts.get('property_type') == '非住宅' else
                        'residential_evidence_ready' if category == 'residential' and
                        valid_address(facts.get('address')) and not facts.get('address_error') else 'needs_evidence')
                    hits = [c['community_id'] for c in store.candidates(merged) if c['eligible']]
                    row['matching_community_ids'] = hits
                    row['association'] = ('existing_association' if record.get('community_id') else
                        'unique_existing_match' if len(hits) == 1 else 'ambiguous' if hits else 'new_candidate')
                except Exception as exc:
                    code = getattr(exc, 'code', type(exc).__name__)
                    row.update(category='deferred' if code in {'paused', 'busy'} else 'fetch_failed', error=str(exc), error_code=code)
                rows.append(row)
        finally:
            if owned:
                client.close()
        return dict(captured_at=now(), mode='read_only_source_evidence', candidates=len(projects),
                    inspected=len(rows), counts=dict(Counter(r['category'] for r in rows)), items=rows,
                    note='仅预览来源证据及可能关联，不执行收录、物化、定位或生产写入；实际收录仍按当前规则判定。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=3, choices=range(1, 21))
    parser.add_argument('--name', action='append')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.registry.resolve().parent):
        parser.error('--output must be outside the production registry directory')
    report = preview(args.registry, limit=args.limit, names=args.name)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('mode', 'candidates', 'inspected', 'counts')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
