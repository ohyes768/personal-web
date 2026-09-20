#!/usr/bin/env python3
"""把 skill-agent-matrix.html 的 registry-data 内嵌 JSON 迁移为 registry.json。

转换规则（design 3.1 + implement.md Task 2）：
- `name` 规范化为确定性 id（小写，非法字符转 `-`）；
- `dir` → `path`（local）；github 条目 `path` 默认 `"."`；
- `repo` → `repository`（去 `.git` 后缀）；
- `theme` → 单个 tag；
- `depends_on` 保留（id 规范化后）；
- `status` 仅接受 active/deprecated，其余值警告跳过；
- local 条目要求目录存在且含 SKILL.md，缺失则警告跳过；
- 版本快照（latest_version/head_commit/checked_at）是运行状态，不写回注册表。

用法：
    uv run python scripts/migrate_registry.py --source-root F:/personal-projects/skills --dry-run
    uv run python scripts/migrate_registry.py --source-root F:/personal-projects/skills
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from src.models import RegistrySkill  # noqa: E402

BLOCK_RE = re.compile(
    r'<script\s+type="application/json"\s+id="registry-data"\s*>(.*?)</script>',
    re.DOTALL,
)
REGISTRY_FILENAME = "registry.json"


def sanitize_id(name: str) -> str:
    """确定性 id：小写 + 非法字符折叠为 `-`（与 models.SkillId pattern 一致）。"""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    return slug


def normalize_repository(url: str) -> str:
    url = url.strip()
    return url[:-4] if url.endswith(".git") else url


def read_html_registry(html_path: Path) -> dict:
    match = BLOCK_RE.search(html_path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{html_path} 中未找到 registry-data 数据块")
    return json.loads(match.group(1))


def convert_skill(raw: dict, source_root: Path) -> tuple[RegistrySkill | None, str]:
    """返回 (转换结果或 None, 说明信息)。"""
    name = raw["name"]
    skill_id = sanitize_id(name)
    status = raw.get("status", "active")
    if status not in ("active", "deprecated"):
        return None, f"[skip] {name}: status={status!r} 不在 active/deprecated 内"

    source = raw.get("source")
    if source == "local":
        rel_path = raw["dir"].replace("\\", "/").strip("/")
        target_dir = (source_root / rel_path).resolve()
        if not target_dir.is_relative_to(source_root):
            return None, f"[skip] {name}: 目录越出源库根 {rel_path}"
        if not (target_dir / "SKILL.md").is_file():
            return None, f"[skip] {name}: 目录缺少 SKILL.md（{rel_path}）"
        entry = {"id": skill_id, "name": name, "source": "local", "path": rel_path}
    elif source == "github":
        entry = {
            "id": skill_id,
            "name": name,
            "source": "github",
            "path": raw.get("path") or ".",
            "repository": normalize_repository(raw["repo"]),
        }
    else:
        return None, f"[skip] {name}: 未知 source={source!r}"

    entry["tags"] = [raw["theme"]] if raw.get("theme") else []
    entry["summary"] = raw.get("summary", "")
    entry["status"] = status
    if raw.get("depends_on"):
        entry["depends_on"] = [sanitize_id(dep) for dep in raw["depends_on"]]

    try:
        return RegistrySkill.model_validate(entry), f"[ok] {name} -> {skill_id}"
    except Exception as exc:  # noqa: BLE001
        return None, f"[skip] {name}: schema 校验失败（{exc}）"


def atomic_write_json(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="迁移 HTML registry-data 到 registry.json")
    parser.add_argument("--source-root", required=True, help="Skills 源库根目录")
    parser.add_argument(
        "--html",
        help="HTML 路径（默认 <source-root>/skill-agent-matrix.html）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印统计，不写文件")
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    if not source_root.is_dir():
        print(f"[x] 源库根不存在: {source_root}")
        return 1
    html_path = Path(args.html).resolve() if args.html else source_root / "skill-agent-matrix.html"
    if not html_path.is_file():
        print(f"[x] HTML 不存在: {html_path}")
        return 1

    legacy = read_html_registry(html_path)

    skills: list[RegistrySkill] = []
    skipped: list[str] = []
    for raw in legacy.get("skills", []):
        skill, message = convert_skill(raw, source_root)
        print(message)
        (skills if skill else skipped).append(skill or message)

    seen_ids: set[str] = set()
    for skill in skills:
        if skill.id in seen_ids:
            print(f"[x] 迁移中止：转换后出现重复 id {skill.id}")
            return 1
        seen_ids.add(skill.id)

    agents = {
        key: {
            "description": cfg.get("description", ""),
            "skills": [sanitize_id(s) for s in cfg.get("skills", [])],
        }
        for key, cfg in legacy.get("agents", {}).items()
    }
    missing_refs = sorted(
        {sid for refs in agents.values() for sid in refs["skills"]} - seen_ids
    )
    for sid in missing_refs:
        print(f"[warn] agents 引用了未迁移的 skill id: {sid}")

    payload = {
        "version": "3.0",
        "updated": date.today().isoformat(),
        "skills": [skill.model_dump(mode="json") for skill in skills],
        "agents": agents,
    }

    print(
        f"\n迁移 {len(skills)} 个 skill，跳过 {len(skipped)} 个，"
        f"agents {len(agents)} 个" + ("（dry-run，未写文件）" if args.dry_run else "")
    )
    if args.dry_run:
        return 0

    out_path = source_root / REGISTRY_FILENAME
    atomic_write_json(out_path, payload)
    print(f"已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
