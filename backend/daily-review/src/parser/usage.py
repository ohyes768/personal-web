"""
~/.dsh/dsh-usage/usage-ledger.json 解析（Host 维护的日汇总账本）。

结构：{"version":1,"days":{"2026-11-11":{"<provider>":{"<model>":{token 计数...}}}}}
文件被运行中 Host 随时原子写 → 一次 open 整读，绝不写。
损坏/缺失返回空列表不抛。
"""
from __future__ import annotations

import json
from pathlib import Path

_TOKEN_KEYS = (
    # (行字段名, ledger 原始键——camelCase 为主，snake_case 兼容)
    ("input_tokens", ("inputTokens", "input_tokens")),
    ("output_tokens", ("outputTokens", "output_tokens")),
    ("cache_read_tokens", ("cacheReadTokens", "cache_read_tokens")),
    ("cache_write_tokens", ("cacheWriteTokens", "cache_write_tokens")),
    ("reasoning_tokens", ("reasoningTokens", "reasoning_tokens")),
)


def _safe_int(v) -> int:
    return int(v) if isinstance(v, (int, float)) else 0


def _pick(usage: dict, keys: tuple[str, ...]) -> int:
    for k in keys:
        if k in usage:
            return _safe_int(usage[k])
    return 0


def _safe_float(v) -> float:
    return float(v) if isinstance(v, (int, float)) else 0.0


def parse_usage_ledger(path: Path, machine: str = "nas") -> list[dict]:
    """整读 usage-ledger.json，平铺为 usage_daily 行列表；损坏/缺失返回空列表。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()  # 一次整读
    except OSError:
        return []
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return []
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, dict):
        return []

    rows: list[dict] = []
    for date, providers in days.items():
        if not isinstance(providers, dict):
            continue
        for provider, models in providers.items():
            if not isinstance(models, dict):
                continue
            for model, usage in models.items():
                if not isinstance(usage, dict):
                    continue
                row = {
                    "machine": machine,
                    "date": str(date),
                    "provider": str(provider),
                    "model": str(model),
                    "calls": _safe_int(usage.get("calls")),
                    "cost": _safe_float(usage.get("cost")),
                }
                for field, raw_keys in _TOKEN_KEYS:
                    row[field] = _pick(usage, raw_keys)
                rows.append(row)
    return rows
