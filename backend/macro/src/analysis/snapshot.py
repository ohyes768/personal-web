"""Deterministic, raw-observation evidence for chart explanations."""
import hashlib
import json
from datetime import date, datetime, timezone

import pandas as pd
from fastapi import HTTPException
from src.analysis.registry import ChartDefinition


def summarize(key: str, label: str, series: pd.Series, derived: bool = False, unit: str = "%", is_rate: bool = True, relative_change: bool = False) -> dict:
    series = series.dropna()
    points = [{"date": day.strftime("%Y-%m-%d"), "value": float(value)} for day, value in series.items()]
    stats = None
    if points:
        change = points[-1]["value"] - points[0]["value"]
        stats = {"start": points[0], "end": points[-1], "change_value": round(change, 6),
                 "change_pp": round(change, 6) if unit == "%" else None,
                 "change_bp": round(change * 100, 4) if unit == "%" and is_rate else None,
                 "change_percent": round(change / points[0]["value"] * 100, 6)
                 if relative_change and points[0]["value"] > 0 and all(p["value"] > 0 for p in points) else None, "min": min(p["value"] for p in points),
                 "max": max(p["value"] for p in points), "count": len(points)}
    # Full-observation statistics; explicit sampling only for model context size.
    stride = max(1, (len(points) + 59) // 60)
    samples = points[::stride]
    if points and (not samples or samples[-1] != points[-1]):
        samples.append(points[-1])
    return {"evidence_id": key, "label": label, "unit": unit, "derived": derived,
            "status": "missing" if not points else "short_sample" if len(points) < 5 else "ok",
            "statistics": stats, "observations": samples, "sampled": len(samples) < len(points)}


def build_snapshot(definition: ChartDefinition, start: date, end: date, service) -> dict:
    if start > end or end > date.today():
        raise HTTPException(422, "请选择有效的历史日期区间")
    try:
        frames = service.load_analysis_observations([s.store for s in (*definition.series, *definition.references)])
    except Exception:
        raise HTTPException(503, "原始数据暂时不可读或正在更新，请稍后重试") from None
    values = {}
    latest = {}
    for item in (*definition.series, *definition.references):
        frame = frames[item.store]
        raw = pd.to_numeric(frame[item.column], errors="coerce") if item.column in frame else pd.Series(dtype=float)
        raw = raw.replace([float("inf"), -float("inf")], float("nan"))
        latest[item.id] = raw.dropna().index[-1].strftime("%Y-%m-%d") if not raw.dropna().empty else None
        if not raw.empty:
            raw = raw[(raw.index >= pd.Timestamp(start)) & (raw.index <= pd.Timestamp(end))]
        values[item.id] = raw
    if not any(not values[s.id].dropna().empty for s in definition.series):
        raise HTTPException(422, "这段时间没有可分析的原始观测，请调整时间范围")
    main = [summarize(s.id, s.label, values[s.id], unit=s.unit, is_rate=s.is_rate, relative_change=s.relative_change) for s in definition.series]
    for item, evidence in zip(definition.series, main):
        evidence["source_as_of"] = latest[item.id]
        evidence["source"] = {"store": item.store, "column": item.column}
    derived = []
    common = pd.concat([values[s.id] for s in definition.series], axis=1).dropna()
    decomposition = None
    if definition.id == "rates.china-bonds" and not common.empty:
        two = common.iloc[:, 0] - common.iloc[:, 1]
        derived.append(summarize("cn_2y", "中国2年国债收益率（10年减利差推导）", two, True))
        decomposition = {"start_date": common.index[0].strftime("%Y-%m-%d"),
                         "end_date": common.index[-1].strftime("%Y-%m-%d"),
                         "count": len(common),
                         "cn_10y_change_bp": round(float(common.iloc[-1, 0] - common.iloc[0, 0]) * 100, 4),
                         "spread_change_bp": round(float(common.iloc[-1, 1] - common.iloc[0, 1]) * 100, 4),
                         "cn_2y_change_bp": round(float(two.iloc[-1] - two.iloc[0]) * 100, 4)}
    evidence = {"chart_id": definition.id, "title": definition.title, "definition_version": definition.version,
                "range": [start.isoformat(), end.isoformat()], "primary": main, "derived": derived,
                "description": definition.description,
                "common_dates": {"count": len(common),
                    "series": [summarize(s.id, s.label, common.iloc[:, i], unit=s.unit,
                        is_rate=s.is_rate, relative_change=s.relative_change)
                        for i, s in enumerate(definition.series)]},
                "references": [summarize(s.id, s.label, values[s.id], unit=s.unit, is_rate=s.is_rate, relative_change=s.relative_change) for s in definition.references],
                "decomposition": decomposition,
                "quality": "partial" if any(s["status"] != "ok" for s in main) or len(common) < 5 else "ok"}
    evidence["snapshot_id"] = hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    evidence["generated_at"] = datetime.now(timezone.utc).isoformat()
    return evidence
