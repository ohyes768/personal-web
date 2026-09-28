# Infant Album Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the standalone catalog script to output only high-confidence 0–1-year-old album candidates and never pad results with school-age content.

**Architecture:** Use Qingting's public 0–1 age-filter path as the platform-labelled source. Use Ximalaya only for albums whose visible title or summary explicitly declares a 0–1-year-old, infant, or baby audience; its general children's chart is not a valid source. Store a distinct age-segment cache so prior all-children output is never reused.

**Tech Stack:** Python standard library, BeautifulSoup, Playwright, unittest.

---

### Task 1: Define age-segment sources and output metadata

**Files:**
- Modify: `scripts/kids-catalog/hot_albums.py`
- Test: `scripts/kids-catalog/test_hot_albums.py`

- [ ] **Step 1: Write failing parser tests**

```python
def test_qingting_uses_0_to_1_source_and_marks_platform_basis(self):
    rows = parse_qingting(FIXTURE)
    self.assertEqual(rows[0]["age_band"], "0-1岁")
    self.assertEqual(rows[0]["age_evidence"], "蜻蜓FM年龄筛选")

def test_ximalaya_rejects_general_children_album(self):
    html = '<div class="album-item"><a href="/album/123"><div class="title">儿童故事</div><div class="description">适合孩子</div></a></div>'
    self.assertEqual(parse_ximalaya(html), [])
```

- [ ] **Step 2: Run the tests to verify failure**

Run: `python -m unittest discover -s scripts/kids-catalog -p test_hot_albums.py`

Expected: FAIL because age metadata and explicit-age filtering do not exist.

- [ ] **Step 3: Add named constants and parser metadata**

```python
AGE_BAND = "0-1岁"
QT = "https://m.qingting.fm/categories/1599/attrs/4394/"
XM_INFANT_PATTERN = re.compile(r"(?:0\s*[-~至到]\s*1\s*岁|0岁\+|婴儿|婴幼儿|宝宝启蒙)")
```

Add `age_band`, `age_evidence`, and `age_confidence` to every accepted row. Preserve the existing `platform` plus `album_id` de-duplication.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m unittest discover -s scripts/kids-catalog -p test_hot_albums.py`

Expected: PASS.

### Task 2: Make incomplete results honest and isolate cache files

**Files:**
- Modify: `scripts/kids-catalog/hot_albums.py`
- Test: `scripts/kids-catalog/test_hot_albums.py`

- [ ] **Step 1: Write failing tests for short valid lists**

```python
def test_choose_allows_short_infant_candidates(self):
    rows = [{"platform": "蜻蜓FM", "album_id": "1"}]
    self.assertEqual(choose(rows, 15, allow_short=True), rows)
```

- [ ] **Step 2: Run the test to verify failure**

Run: `python -m unittest discover -s scripts/kids-catalog -p test_hot_albums.py`

Expected: FAIL because `choose` raises when the list contains fewer than 15 albums.

- [ ] **Step 3: Permit a short list only in infant mode**

Use `allow_short=True` for both sources. Generate paths such as `data/hot-albums/2026-09-0-1.json`; retain original `2026-09.json` untouched. Set `requested_count` to 30 and `actual_count` to the returned count.

- [ ] **Step 4: Render truthful report text**

Change the heading from a fixed 30 count to the actual count. Include one concise explanation: only platform age filtering or explicit age declarations were accepted; missing entries were not substituted.

- [ ] **Step 5: Run tests to verify pass**

Run: `python -m unittest discover -s scripts/kids-catalog -p test_hot_albums.py`

Expected: PASS.

### Task 3: Update usage documentation and perform a live bounded run

**Files:**
- Modify: `scripts/kids-catalog/README.md`
- Create: `scripts/kids-catalog/data/hot-albums/YYYY-MM-0-1.json`
- Create: `scripts/kids-catalog/data/hot-albums/YYYY-MM-0-1.csv`
- Create: `scripts/kids-catalog/data/hot-albums/YYYY-MM-0-1.md`

- [ ] **Step 1: Document the strict acceptance rule**

State that Qingting uses its 0–1-year filter, Ximalaya requires an explicit visible age declaration, ordinary children's, bedtime, and nursery-rhyme labels alone are rejected, and results may be fewer than 30.

- [ ] **Step 2: Run the test suite**

Run: `python -m unittest discover -s scripts/kids-catalog -p test_hot_albums.py`

Expected: PASS.

- [ ] **Step 3: Run the script once and validate generated records**

Run: `python scripts/kids-catalog/hot_albums.py`

Expected: a 0–1-year markdown/CSV/JSON snapshot with unique `platform` plus `album_id` values and only accepted age-evidence values.

- [ ] **Step 4: Re-run the script to verify cache reuse**

Run: `python scripts/kids-catalog/hot_albums.py`

Expected: it reuses the same 0–1-year snapshot without a second source collection.

### Self-review

- The plan covers the confirmed strict source rule, short honest output, metadata, cache isolation, documentation, unit tests, live run, and cache check.
- No placeholder or ambiguous fallback is included.
- `age_band`, `age_evidence`, and `age_confidence` are consistently defined in Task 1 and consumed in Tasks 2–3.
