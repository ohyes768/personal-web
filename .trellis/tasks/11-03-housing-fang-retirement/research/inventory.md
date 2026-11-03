# 源码盘点与证据（2026-11-03）

只读搜索源码，不访问生产服务。GitNexus 工具返回 No indexed repositories，改用源码引用检查。行号为规划时位置，实施前应重新检索。

## 处置分类

- 删除：fang_rentals.py、fang_detail_cache.py、fang_request_policy.py、fetch_fang_rentals.py、FANG_RENTALS.md 及专属失效测试。先迁出共用类型。
- 修改：刷新、当前来源选择、API/coverage、目录初始化/采集、用途分类/自动审核、前端当前来源与容器 seed。
- 保留：历史数据、身份标签、人工决定、迁移报告、最小 410 路由和跨来源隔离测试。保留不代表参与当前计算。
- 历史目录/迁移流程必须保持数据保护；不批量重审，不触碰既有标记。

## 全部引用文件

下表的数字为含引用行数，不是可删除行数；排除了仅含 /zufang/ 的幸福里路径。

### 后端运行代码（26 个文件）

| 文件 | 引用行数 | 首次位置 |
|---|---:|---:|
| `backend/housing-map/src/api/directory_routes.py` | 4 | 152 |
| `backend/housing-map/src/api/rental_routes.py` | 5 | 66 |
| `backend/housing-map/src/api/rental_source_routes.py` | 2 | 72 |
| `backend/housing-map/src/services/collection_pipeline_migration.py` | 1 | 51 |
| `backend/housing-map/src/services/community_admission.py` | 1 | 36 |
| `backend/housing-map/src/services/community_auto_review.py` | 5 | 144 |
| `backend/housing-map/src/services/community_directory.py` | 6 | 76 |
| `backend/housing-map/src/services/community_registry.py` | 4 | 410 |
| `backend/housing-map/src/services/directory_collection.py` | 13 | 290 |
| `backend/housing-map/src/services/directory_coverage.py` | 1 | 21 |
| `backend/housing-map/src/services/directory_migration.py` | 1 | 73 |
| `backend/housing-map/src/services/fang_detail_cache.py` | 7 | 17 |
| `backend/housing-map/src/services/fang_rentals.py` | 30 | 1 |
| `backend/housing-map/src/services/fang_request_policy.py` | 14 | 1 |
| `backend/housing-map/src/services/rental_reference/__init__.py` | 1 | 1 |
| `backend/housing-map/src/services/rental_reference/association.py` | 17 | 41 |
| `backend/housing-map/src/services/rental_reference/discovery_checkpoint.py` | 1 | 13 |
| `backend/housing-map/src/services/rental_reference/probe.py` | 3 | 17 |
| `backend/housing-map/src/services/rental_reference/providers.py` | 4 | 3 |
| `backend/housing-map/src/services/rental_reference/refresh.py` | 15 | 32 |
| `backend/housing-map/src/services/rental_reference/sources.py` | 14 | 13 |
| `backend/housing-map/src/services/rental_reference/storage.py` | 1 | 195 |
| `backend/housing-map/src/services/rental_reference/xingfuli_sources.py` | 2 | 220 |
| `backend/housing-map/src/services/residential_classifier.py` | 42 | 5 |
| `backend/housing-map/src/services/xingfuli_rentals.py` | 1 | 18 |
| `backend/housing-map/src/services/xingfuli_transport.py` | 1 | 18 |

### 脚本与说明（4 个文件）

| 文件 | 引用行数 | 首次位置 |
|---|---:|---:|
| `backend/housing-map/scripts/FANG_RENTALS.md` | 8 | 1 |
| `backend/housing-map/scripts/fetch_fang_rentals.py` | 5 | 1 |
| `backend/housing-map/scripts/filter_residential_communities.py` | 6 | 54 |
| `backend/housing-map/scripts/XINGFULI_RENTALS.md` | 2 | 3 |

### 前端运行代码（5 个文件）

| 文件 | 引用行数 | 首次位置 |
|---|---:|---:|
| `apps/housing-map/src/components/community/DirectoryCards.tsx` | 2 | 34 |
| `apps/housing-map/src/components/community/UseReviewPanel.tsx` | 1 | 24 |
| `apps/housing-map/src/components/rental/RentalSourceManager.tsx` | 2 | 15 |
| `apps/housing-map/src/lib/rental-sources.ts` | 2 | 2 |
| `apps/housing-map/src/lib/rental-types.ts` | 1 | 95 |

### 相关测试（35 个文件）

| 文件 | 引用行数 | 首次位置 |
|---|---:|---:|
| `backend/housing-map/tests/test_community_auto_review_integration.py` | 1 | 13 |
| `backend/housing-map/tests/test_community_enrichment.py` | 1 | 70 |
| `backend/housing-map/tests/test_community_missing_address.py` | 2 | 87 |
| `backend/housing-map/tests/test_community_registry.py` | 6 | 7 |
| `backend/housing-map/tests/test_community_review.py` | 4 | 51 |
| `backend/housing-map/tests/test_directory_api.py` | 6 | 16 |
| `backend/housing-map/tests/test_directory_collection.py` | 23 | 23 |
| `backend/housing-map/tests/test_directory_flow.py` | 7 | 63 |
| `backend/housing-map/tests/test_directory_integration.py` | 1 | 12 |
| `backend/housing-map/tests/test_fang_rentals.py` | 14 | 3 |
| `backend/housing-map/tests/test_fang_rentals_run.py` | 12 | 7 |
| `backend/housing-map/tests/test_fang_resilience.py` | 26 | 6 |
| `backend/housing-map/tests/test_filter_residential_communities.py` | 5 | 28 |
| `backend/housing-map/tests/test_matching_speed.py` | 2 | 41 |
| `backend/housing-map/tests/test_name_similarity.py` | 1 | 6 |
| `backend/housing-map/tests/test_rental_api.py` | 8 | 67 |
| `backend/housing-map/tests/test_rental_association_flow.py` | 27 | 25 |
| `backend/housing-map/tests/test_rental_continue.py` | 2 | 8 |
| `backend/housing-map/tests/test_rental_probe.py` | 1 | 373 |
| `backend/housing-map/tests/test_rental_providers.py` | 19 | 10 |
| `backend/housing-map/tests/test_rental_refresh.py` | 21 | 29 |
| `backend/housing-map/tests/test_rental_sources.py` | 14 | 15 |
| `backend/housing-map/tests/test_rental_split.py` | 5 | 9 |
| `backend/housing-map/tests/test_rental_statistics.py` | 3 | 20 |
| `backend/housing-map/tests/test_rental_storage.py` | 2 | 25 |
| `backend/housing-map/tests/test_rental_xingfuli_sources.py` | 1 | 181 |
| `backend/housing-map/tests/test_residential_classifier.py` | 19 | 22 |
| `backend/housing-map/tests/test_use_review_confirm.py` | 1 | 43 |
| `backend/housing-map/tests/test_use_review_scenario.py` | 1 | 63 |
| `apps/housing-map/tests/community-management.test.cjs` | 3 | 36 |
| `apps/housing-map/tests/directory-flow.test.cjs` | 1 | 63 |
| `apps/housing-map/tests/rental-dashboard.test.cjs` | 1 | 227 |
| `apps/housing-map/tests/rental-probe.test.cjs` | 3 | 85 |
| `apps/housing-map/tests/rental-reference.test.cjs` | 4 | 40 |
| `apps/housing-map/tests/rental-sources.test.cjs` | 3 | 18 |

## 关键证据定位

- `backend/housing-map/src/services/fang_rentals.py:265`：`class SeedRunResult:`
- `backend/housing-map/src/services/fang_rentals.py:286`：`class RentalCrawlCancelled(Exception):`
- `backend/housing-map/src/services/fang_rentals.py:295`：`class CrawlProgress:`
- `backend/housing-map/src/services/rental_reference/sources.py:35`：`class SourceStore:`
- `backend/housing-map/src/services/rental_reference/sources.py:165`：`def source_page(url: str) -> str:`
- `backend/housing-map/src/services/rental_reference/sources.py:174`：`def discover(community: dict, *, keyword: str = '', source_url: str = '', client_factory=FangClient,`
- `backend/housing-map/src/api/rental_source_routes.py:54`：`def sources():`
- `backend/housing-map/src/api/rental_source_routes.py:65`：`def source(community_id: str):`
- `backend/housing-map/src/api/rental_source_routes.py:71`：`def search(community_id: str, request: SearchRequest):`
- `backend/housing-map/src/api/rental_source_routes.py:76`：`def confirm(community_id: str, request: ConfirmRequest):`
- `backend/housing-map/src/api/rental_source_routes.py:81`：`def remove(community_id: str):`
- `backend/housing-map/src/api/rental_source_routes.py:92`：`def reject(community_id: str, source_id: str):`
- `backend/housing-map/src/services/rental_reference/association.py:18`：`def eligible_communities(registry):`
- `backend/housing-map/src/services/rental_reference/association.py:76`：`def read_review(registry, cid):`
- `backend/housing-map/src/services/rental_reference/association.py:137`：`def decide(registry, cid, action, candidate_id=None):`
- `backend/housing-map/src/services/rental_reference/association.py:180`：`def prepare_sources(registry, cancel, progress, discover, *, delay=5, budget=5, paused_reason=None):`
- `backend/housing-map/src/services/residential_classifier.py:54`：`def classify(*, community_id, tmsf_property_type=None, fang_samples=None, name=""):`
- `backend/housing-map/src/services/residential_classifier.py:98`：`def classify_sources(records, property_types=None):`
- `backend/housing-map/src/services/residential_classifier.py:127`：`def classify_directory(*, communities, property_types, fang_samples_by_community=None):`
- `backend/housing-map/src/services/community_directory.py:14`：`def prepare_directory(data_dir):`
- `backend/housing-map/src/services/community_directory.py:107`：`def _import_fang(db, item, cid, status):`
- `backend/housing-map/src/services/community_registry.py:437`：`if r['source'] in {'fang', 'xingfuli'} and db.execute(`
- `backend/housing-map/src/services/community_registry.py:506`：`for provider in ('fang', 'xingfuli'):`
- `backend/housing-map/Dockerfile:31`：`COPY data/rental_community_mappings.json ./seed-data/rental_community_mappings.json`
