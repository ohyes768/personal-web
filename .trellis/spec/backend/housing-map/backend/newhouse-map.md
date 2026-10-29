# New-house projects on the shared map

> Extends [New residential projects and enrichment](./community-enrichment.md). That spec owns how identity, use and price evidence are *collected*; this one owns how the same evidence reaches the shared map and how new houses are compared with nearby second-hand listings.

## 1. Scope / Trigger
Use when changing the map's housing-type switch, new-house project points, position credibility, price isolation between markets, or the "nearby second-hand" comparison entry.

## 2. Signatures
- `community_market.project_view(records)` — project evidence from matched sources: `{project_id, project_name, sale_status, identity_url, captured_at}` or `None`. Prefers a `source_kind='project'` source over a community source carrying project identity.
- `community_market.position_evidence_view(community, records, coordinate)` — `{source, verified, address}`. `verified` is true only for `amap` (fresh POI) and `manual` (human published) evidence; `historical_amap` is never fresh verification.
- `community_views(...)` — additionally projects `project` and `position_evidence` alongside the existing `market_state` / `market_state_conflict`.
- `GET /api/communities` — every record carries `market_state`, `market_state_conflict`, `project`, `position`. `_assemble_community` is shared with `/api/score`, so both paths stay consistent.
- Frontend `lib/market-map.ts` — `marketStateOf`, `isSecondHand`, `isNewHouse`, `visibleCommunities`, `haversineMeters`, `nearbySecondHand`, `newHousePriceText`, `secondHandPriceText`, `MARKET_MODE_OPTIONS`, `MARKET_STATE_LABELS`, `NEARBY_DEFAULT_RADIUS_METERS`.

## 3. Contracts
- **Market state is explicit.** `new_house` requires explicit 在售/尾盘/待售 project status; 售完 projects read as `second_hand` while keeping their project metadata. A missing or invalid field is `unknown`, never `second_hand`. `unknown` appears only in the "全部" mode and is labelled 房源类型待核实.
- **No price borrowing.** New houses have no trusted price source yet, so their price is 暂无价格 and must never be filled from the second-hand snapshot fields. Second-hand-only aggregates (average price, listing/deal counts, price-color legend, price scale) are explicitly restricted to `isSecondHand`. The price color scale applies to second-hand only; new-house points use a fixed category color.
- **Project point, not a placeholder.** A new house without a boundary renders as a project point with a 新 badge and its name — never the second-hand 100m "?" placeholder, and it offers no building-cluster generation entry. At low zoom only the badge shows; the name appears when zoomed in.
- **Position credibility is per point.** A verified position renders solid; a position that is merely eligible for display renders hollow and says 位置待核实. A community with no valid coordinates draws no point at all.
- **The switch preserves the view.** Changing housing type changes only the visible set — map center, zoom, search, district, property type, POI layers and the deal/listing price switch all survive. The switch clears the detail of an object that just left the view.
- **Comparison is anchored.** "看附近二手房" uses a 1.5 km straight-line radius over the *currently visible* second-hand set, sorted by distance then `community_id`. Price-less second-hand entries still appear. The radius and the active filters are stated in the UI, and an empty result says so instead of inventing data.
- **Distance is a real distance.** `haversineMeters` with R=6371000 m; never a degree subtraction and never presented as walking distance.

## 4. Validation & Error Matrix
Missing `market_state` → `unknown`, visible in 全部 only. Sold-out → `second_hand` with project evidence retained. Mixed new-house/second-hand evidence → `new_house` plus `market_state_conflict`. Missing coordinates → not on the map, still admitted in the directory, counted under `missing_coordinates`. Unknown source → `unknown`. No trusted project price → 暂无价格.

## 5. Good / Base / Bad Cases
Good: 在售 project with a manual position → solid project point, project evidence shown, 暂无价格, nearby second-hand listed by distance. Base: 售完 project → second-hand on the map, project metadata still visible. Bad: defaulting unknown to second-hand, filling a new-house price from `listing_avg_price`, drawing a "?" placeholder for a new house, or labelling a `historical_amap` coordinate as verified.

## 6. Tests Required
`tests/test_newhouse_map_api.py`: market state per class, sold-out reclassification with retained evidence, no second-hand price on new houses (including when a second-hand snapshot exists for the same community), missing coordinates staying off the map, position evidence by source, conflict flagging. Frontend `tests/newhouse-map.test.cjs`: unknown never defaults to second-hand, unknown only in 全部, 1500 m boundary inclusion, distance ordering, price-less entries retained, new-house price text free of second-hand numbers. `tests/newhouse-marker-layer.test.cjs` and `tests/newhouse-detail.test.cjs` cover marker styling and the detail panel.

Browser QA uses an isolated `HOUSING_DATA_DIR` seeded by `scripts/seed_newhouse_map_qa.py` (new-house/second-hand mix: 在售/待售/售完, verified/unverified position, missing coordinates, near/far/price-less second-hand). Check the switch, project point, nearby comparison, switch-back, and that the switch preserves map center and zoom on 1440px and 375px.

### 6.1 Narrow-screen layout
The housing-type switch is a **persistent dock** (`.market-mode-dock`), not part of the collapsible control panel: below 768px the panel is an overlay that would otherwise hide the switch entirely. On narrow screens the control panel is an overlay (not a full-width document-flow block) and starts collapsed, because a document-flow panel pushes the map down and covers the community markers, making them unclickable. The dock shifts right of the 560px detail panel on desktop and hides on narrow screens while the detail is open.

### 6.2 Price snapshots are keyed by source id
In registry mode `load_price_snapshots` maps snapshot rows to communities through the **source** id, not the community id. Isolated QA fixtures must use the source id in the snapshot row, or prices silently load as empty.

## 7. Wrong vs Correct
Wrong: infer market type from name or from zero listings, or reuse `community.price` for a new house. Correct: read the explicit projected field, and treat a missing field as unknown.
