# 提交计划（用户已批准提交并推送）

1. `feat(housing-map): add manual association for auction properties`

- apps/housing-map/src/app/page.tsx
- apps/housing-map/src/components/auction/AuctionDataList.tsx
- apps/housing-map/src/components/auction/AuctionPendingAssociations.tsx
- apps/housing-map/src/components/auction/AuctionPendingAssociations.module.css
- apps/housing-map/src/lib/auction-types.ts
- apps/housing-map/tests/auction-list.test.cjs
- backend/housing-map/src/api/auction_routes.py
- backend/housing-map/src/services/auction_refresh.py
- backend/housing-map/src/services/auction_association.py
- backend/housing-map/src/services/community_registry.py
- backend/housing-map/tests/test_auction_association.py
- .trellis/spec/guides/housing-map-auctions.md
- .trellis/tasks/10-13-housing-auction-manual-association/（规划与验收文档）

## 非本任务改动：全部排除

- apps/housing-map/src/app/globals.css
- apps/housing-map/src/components/community/CommunityManagement.tsx
- apps/housing-map/src/components/rental/RentalRefreshButton.tsx
- apps/housing-map/src/lib/rental-dashboard.ts
- apps/housing-map/src/lib/rental-types.ts
- apps/housing-map/src/lib/use-rental-refresh.ts
- apps/housing-map/tests/rental-dashboard.test.cjs
- backend/housing-map/src/api/rental_routes.py
- backend/housing-map/src/api/rental_source_routes.py
- backend/housing-map/src/services/rental_reference/refresh.py
- backend/housing-map/tests/test_rental_api.py
- .pnpm-store/
- .trellis/tasks/10-13-housing-rental-update-flow/
- apps/housing-map/src/components/rental/RentalAssociationReview.tsx
- backend/housing-map/src/services/rental_reference/association.py
- backend/housing-map/tests/test_rental_association_flow.py
