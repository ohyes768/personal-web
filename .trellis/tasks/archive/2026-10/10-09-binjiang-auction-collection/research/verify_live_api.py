import json
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / "backend/housing-map"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.auction_routes import router
from src.services.auction_fetcher import AuctionClient, normalize_auction
from src.services.data_loader import load_communities

app = FastAPI()
app.include_router(router, prefix="/api")
with TestClient(app) as api:
    assert api.post("/api/auctions/refresh?max_pages=5&limit=3").status_code == 202
    assert api.post("/api/auctions/refresh?limit=3").status_code == 409
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = api.get("/api/auctions/refresh").json()["data"]
        if not state["running"]:
            break
        time.sleep(0.25)
    assert state["phase"] == "done", state
    records = api.get("/api/auctions").json()["data"]
    assert records["total"] >= 3
    print(json.dumps({"refresh": state["result"], "query_total": records["total"]}))

client = AuctionClient()
try:
    row = normalize_auction(client.detail(454711), load_communities())
    assert row["deal_price_yuan"] == 4760000
    assert row["area_m2"] == 149.3
    assert row["deal_unit_price"] == 31882
    (Path(__file__).parent / "verified-deal.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print("verified 454711: deal_price=4760000 area=149.3 unit_price=31882")
finally:
    client.close()
