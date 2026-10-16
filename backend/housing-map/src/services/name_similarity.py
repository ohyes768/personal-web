"""Similarity scoring for Chinese community names.

Fuses character-level metrics (RapidFuzz) over the specialized name — generic
suffixes like 花园 stripped, digits kept because 分期 matters — with an untoned
pinyin fallback for homophone variants. Different phase markers (一期 vs 二期)
never match: 字面像但不是一家的典型. Scores gate the single-candidate auto-bind
and order the manual review list; they are evidence, never a sole verdict.
"""
import re
import unicodedata

from pypinyin import lazy_pinyin
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

AUTO_THRESHOLD = 0.92

# 通名 (generic community suffixes) carry no identity; kept lowercase-insensitive
# via normalized() first. Extend as new source naming shows up.
GENERIC_NAMES = ('花园', '小区', '家园', '公寓', '雅苑', '公馆', '广场', '大厦', '中心',
                 '人家', '新村', '苑', '府', '里', '湾', '城', '庭', '郡', '轩', '阁',
                 '邸', '庄', '居')
PHASE = re.compile(r'[一二三四五六七八九十\d]+期')


def normalized(value: str) -> str:
    """Identical to community_registry.normalized, kept local to avoid import cycles."""
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).casefold()


def specialize(name: str) -> str:
    stripped = normalized(name)
    for word in GENERIC_NAMES:
        stripped = stripped.replace(word, '')
    return stripped


def phase_marker(name: str) -> str:
    match = PHASE.search(normalized(name))
    return match.group(0) if match else ''


def pinyin_key(name: str) -> str:
    return ''.join(lazy_pinyin(name))


def name_similarity(a: str, b: str) -> float:
    """Fused 0..1 similarity; phases conflicting short-circuits to zero."""
    marker_a, marker_b = phase_marker(a), phase_marker(b)
    if marker_a and marker_b and marker_a != marker_b:
        return 0.0
    specialized_a, specialized_b = specialize(a), specialize(b)
    if not specialized_a or not specialized_b:
        return 0.0
    scores = [fuzz.ratio(specialized_a, specialized_b) / 100,
              JaroWinkler.normalized_similarity(specialized_a, specialized_b)]
    if min(len(specialized_a), len(specialized_b)) >= 3:
        # partial_ratio on very short names would score containment trivially high.
        scores.append(fuzz.partial_ratio(specialized_a, specialized_b) / 100)
    scores.append(fuzz.ratio(pinyin_key(specialized_a), pinyin_key(specialized_b)) / 100)
    return round(max(scores), 4)


def best_similarity(name: str, candidate: dict) -> float:
    """Best score of `name` against a candidate's known names (name/alias/aliases)."""
    names = [candidate.get('community_name'), candidate.get('community_alias'),
             *(candidate.get('aliases') or [])]
    scores = [name_similarity(name, n) for n in names if n]
    return max(scores, default=0.0)
