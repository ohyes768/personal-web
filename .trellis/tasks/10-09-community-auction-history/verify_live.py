"""复核真实成交详情、增量保存并验证当前查询契约。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend/housing-map'))
from src.services.auction_fetcher import AuctionClient, normalize_auction, now_iso
from src.services.auction_store import AUCTION_PATH, StoreLock, write_store
from src.services.data_loader import load_communities
from src.services.auction_history import get_history

client = AuctionClient()
try:
    record = normalize_auction(client.detail('454711'), load_communities())
finally:
    client.close()
assert record['deal_price_yuan'] == 4760000 and record['area_m2'] == 149.3
with StoreLock(AUCTION_PATH):
    write_store(AUCTION_PATH, [record], {'complete': False, 'pages': 0, 'processed': 1,
                'matched': 1, 'saved': 1, 'finished_at': now_iso(), 'dry_run': False,
                'scope': '单条已知成交详情复核，非列表遍历'})
result = get_history('10001742')
assert result['total'] >= 1
assert any(r['auction_id'] == '454711' for r in result['records'])
Path(__file__).with_name('verified-history.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'community_id': result['community_id'], 'stats': result['stats']}, ensure_ascii=False))
