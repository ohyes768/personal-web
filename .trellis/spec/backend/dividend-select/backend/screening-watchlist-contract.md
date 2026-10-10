# Dividend screening and watchlist contract

## 1. Scope / Trigger
Applies to the screening Tab, historical financial fields, screening API and batch favorites. Read with financial-quarterly-contract.md and code-type-guidelines.md.

## 2. Signatures
- POST /api/dividend/stocks/screen: ScreeningRequest → ScreeningResponse.
- POST /api/dividend/favorites/batch: {codes: string[]} → {items, favorites}.
- FinancialFetcher adds annual ROE history and previous adjacent quarter; FinancialReader.row_to_data converts a cached row without rereading the file.

## 3. Contracts
Defaults: min_yield=3.5, min_roe=10, min_roe_avg_3y=10. Numeric thresholds are finite values in [0,100]. The frontend saves one set of conditions in localStorage and restores defaults on request.
Screening starts with the collected pool, never an already threshold-filtered frontend list. The current dividend window is explicitly 2023/2024/2025, inherited from existing data; do not advertise automatically rolling years.
Eligible requires continuous dividend, yield threshold, latest annual ROE threshold, consecutive three-year ROE completeness and mean threshold, annual adjusted profit YOY >=0, and two adjacent single-quarter YOYs not both negative. Current yield is display-only.
Reasons represent failure/missing facts; warnings highlight one negative quarter. A definite failure takes precedence over missing data. Otherwise missing required data means insufficient_data.
Annual ROE is weighted annual ROE from 12-31 statements, never quarterly ROE. CSV fields: ROE年度, 近3年平均ROE, 近3年ROE历史 (JSON [{year,value}]), 前一季度扣非同比(%), 前一季度. ROE average preserves precision. Invalid/nonfinite numeric cells become null.
Response contains counts, conditions snapshot, dividend_years, dividend and financial file update times and each stock's actual report labels.
Batch favorites accepts 1–1000 string codes, validates six ASCII digits per item, deduplicates and returns added/already_exists/failed. One locked atomic write preserves old notes/alerts; disk failure restores memory and marks newly added rows failed. It never enables monitoring or removes stocks.
Favorites are loaded independently of screening and old yield threshold. tab=screening, tab=alerts, fav=1 and legacy tab=watchlist must remain navigable even when a filtered list is empty.

## 4. Validation & Error Matrix
| Input/state | Result |
|---|---|
| Two adjacent negative quarters | excluded |
| One negative, other zero/positive | allowed with warning if other gates pass |
| Missing quarter/base zero/nonadjacent labels | insufficient unless another gate fails |
| Missing ROE year/value | insufficient unless another gate fails |
| NaN/infinity in CSV | null; must not crash JSON serialization |
| Invalid batch code | failed item; valid peers still processed |
| Disk write fails | added items failed, memory restored |
| Old cache lacks schema | financial/status needs_update=true, missing_schema_columns listed |
| Old row remains incomplete after partial refresh | insufficient; do not treat global column existence as row completeness |

## 5. Good / Base / Bad Cases
Good: annual YOY +2%, quarters -10%/+2%, both ROE thresholds met → eligible with warning.
Base: quarters 0%/-10% → not excluded by two-quarter rule.
Bad: quarters -10%/-5% → excluded despite improvement; Q1 plus an older Q3 cannot form a consecutive pair.

## 6. Tests Required
Financial tests: three consecutive annual values, missing year/null/nonfinite values, Q1/Q4 transition, cumulative single-quarter derivation, prior-year zero/negative base, CSV roundtrip and old cache.
Screening tests: boundary inclusion, failure precedence, absent history, adjacent labels and current yield independence.
Batch tests: duplicates, metadata preservation, mixed valid/invalid codes, disk failure rollback and API shape.
Browser tests: empty old list does not hide new Tab, persisted conditions/reset, failed favorite retry, legacy favorites outside threshold.

## 7. Wrong vs Correct
Wrong: filter frontend's current list; missing required data silently passes; deleting candidates also deletes favorites.
Correct: evaluate the complete collected pool with three states; favorites preserve user intent independently.
Wrong: ordinary incremental refresh is assumed to backfill old financial rows.
Correct: initial migration uses full-pool force=true financial refresh, then reruns screening. Genuine source gaps remain missing rather than causing endless auto retries.
