# Evidence and decisions
- Existing fetch_one selects latest 12-31 row for ROE; annual adjusted amount was not persisted. Add it directly from that row, independent of needing two rows for YOY.
- Existing FinancialReader.row_to_data sanitizes nonfinite CSV values and is reused by stock API; extend this boundary.
- Existing status endpoint compares SCREENING_FINANCIAL_COLUMNS, enabling additive old-cache migration notice.
- Retain adjacent label requirement: old/nonadjacent quarterly facts cannot silently qualify as the recent pair. Within an identified adjacent pair, a finite severe quarter is a definite failure even when its peer value is missing.
- Keep existing conditions storage key and decode missing new field to 30, preserving older ROE/yield/exchange preferences.
- No extra stock gates or market recommendations.
