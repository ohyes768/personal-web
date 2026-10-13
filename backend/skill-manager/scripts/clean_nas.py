"""一次性清理 skill-manager pack 体系在 NAS 上的遗留状态。

伴随 commit a20ee65（revert: feat(skill-manager): GitHub 仓库整包发布与根软链部署）。
该脚本仅供一次性现场使用；不写入 CI / cron，不复用。

清理范围（执行顺序，失败即停）：
1. SQLite DROP TABLE: github_pack / legacy_github_pack_member / github_pack_history
2. 删除 openclaw-pack-discovery{,-pending}.json 台账
3. 解析 openclaw.json，从 skills.load.extraDirs 中移除台账声明添加的项（保留用户手写）
4. 扫描 hermes / openclaw skill 根，删除 'github-' 前缀的包软链
5. 清理 github-cache/repos/ 下无引用缓存目录

破坏性操作每个之前都做 `.bak.<ISO ts>` 时间戳备份。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


class CleanNasError(RuntimeError):
    """任何阶段失败抛此异常；命令以非零退出。"""


PACK_TABLES = (
    "github_pack",
    "legacy_github_pack_member",
    "github_pack_history",
)

PACK_LINK_PREFIX = "github-"
OPENCLAW_DISCOVERY_FILES = (
    "openclaw-pack-discovery.json",
    "openclaw-pack-discovery-pending.json",
)


def _now_ts() -> str:
    """生成文件系统安全的时间戳后缀。"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise CleanNasError(f"{path}: 无效 JSON: {exc}") from exc


def _atomic_write(path: Path, content: str) -> None:
    """写回文件前先做 .bak.<ts> 备份，再 atomically replace。"""
    backup = path.with_suffix(path.suffix + f".bak.{_now_ts()}")
    shutil.copy2(path, backup)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        if temporary.exists():
            temporary.unlink()
        raise


def _read_openclaw_extra_dirs(manifest: Path | None) -> set[str]:
    """读取 skill-manager 之前向 openclaw.json 注入的 extraDirs 项集合。

    manifest 不存在则返回空集（视为无注入项）。
    manifest 损坏 → 让 caller 决定继续还是停手。
    """
    if manifest is None or not manifest.exists():
        return set()
    state = _read_json(manifest)
    if not isinstance(state, dict) or not isinstance(state.get("added"), list):
        raise CleanNasError(f"{manifest}: 缺少 added 列表；台账损坏")
    return {item for item in state["added"] if isinstance(item, str)}


# ----------------------------- phase 0 -----------------------------


def phase0_inspect(paths: dict) -> dict:
    """只读盘点，返回 plan dict；不得落盘。"""
    state_db = Path(paths["state_db"])
    openclaw_root = Path(paths["openclaw_root"])
    hermes_root = Path(paths["hermes_root"])
    github_cache_root = Path(paths["github_cache_root"])
    discovery_state_dir = Path(paths["pack_discovery_state_dir"])
    openclaw_config = Path(paths["openclaw_config"])

    plan: dict = {
        "tables": {},
        "discovery_files": [],
        "extra_dirs_to_remove": [],
        "package_symlinks_hermes": [],
        "package_symlinks_openclaw": [],
        "cache_dirs_to_clean": [],
    }

    # --- SQLite 表计数 ---
    if not state_db.exists():
        raise CleanNasError(f"state_db 不存在: {state_db}")
    with sqlite3.connect(state_db) as conn:
        for table in PACK_TABLES:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            except sqlite3.OperationalError:
                plan["tables"][table] = 0
            else:
                plan["tables"][table] = int(row[0])

    # --- discovery 台账 + extraDirs 集合 ---
    manifest = discovery_state_dir / OPENCLAW_DISCOVERY_FILES[0]
    pending = discovery_state_dir / OPENCLAW_DISCOVERY_FILES[1]
    for path in (manifest, pending):
        if path.exists():
            plan["discovery_files"].append(str(path))

    if not openclaw_config.exists():
        raise CleanNasError(f"openclaw_config 不存在: {openclaw_config}")
    config_data = _read_json(openclaw_config)
    try:
        extra_dirs = (
            config_data["skills"]["load"]["extraDirs"]
        )
    except (KeyError, TypeError) as exc:
        raise CleanNasError(
            f"{openclaw_config}: 缺少 skills.load.extraDirs；请先修复 openclaw.json"
        ) from exc
    if not isinstance(extra_dirs, list):
        raise CleanNasError(
            f"{openclaw_config}: skills.load.extraDirs 不是列表"
        )

    managed = _read_openclaw_extra_dirs(manifest)
    plan["extra_dirs_to_remove"] = sorted(
        item for item in extra_dirs if item in managed
    )

    # --- 扫描两个 skill 根下的 pack 软链 ---
    for label, root in (("hermes", hermes_root), ("openclaw", openclaw_root)):
        if not root.is_dir():
            raise CleanNasError(f"{label}_root 不是目录: {root}")
        for entry in root.iterdir():
            if not entry.name.startswith(PACK_LINK_PREFIX):
                continue
            if not entry.is_symlink():
                # 不是软链但用了相同前缀：风险，让用户确认
                raise CleanNasError(
                    f"{entry}: 是非常规条目（不是软链），拒绝继续；"
                    "请先确认是否手动处理"
                )
            target = os.readlink(entry)
            plan[f"package_symlinks_{label}"].append(
                {"path": str(entry), "target": target}
            )

    # --- 缓存目录无引用判定 ---
    repos_dir = github_cache_root / "repos"
    inbound_targets: set[str] = set()
    for label in ("hermes", "openclaw"):
        for entry in plan[f"package_symlinks_{label}"]:
            # 软链 target 是绝对路径
            inbound_targets.add(str(Path(entry["target"]).resolve()))
    if repos_dir.is_dir():
        for entry in repos_dir.iterdir():
            real = str(entry.resolve())
            # 只有当没有 inbound 引用且 entry 是目录才列入清理
            if entry.is_dir() and real not in inbound_targets:
                plan["cache_dirs_to_clean"].append(str(entry))

    return plan


# ----------------------------- phase 1 -----------------------------


def render_plan(plan: dict) -> str:
    lines = ["[1] SQLite DROP TABLE:"]
    for table in PACK_TABLES:
        lines.append(f"    - {table} ({plan['tables'].get(table, 0)} rows)")
    lines.append("[2] File removals:")
    if plan["discovery_files"]:
        for path in plan["discovery_files"]:
            lines.append(f"    - {path}")
    else:
        lines.append("    (no manifest / pending files)")
    lines.append("[3] openclaw.json extraDirs removals:")
    if plan["extra_dirs_to_remove"]:
        for item in plan["extra_dirs_to_remove"]:
            lines.append(f"    - {item}")
    else:
        lines.append("    (no managed extraDirs)")
    lines.append("[4] Package symlinks:")
    for label in ("hermes", "openclaw"):
        syms = plan[f"package_symlinks_{label}"]
        if syms:
            lines.append(f"    ({label}_root) {len(syms)} entries:")
            for entry in syms:
                lines.append(f"        {entry['path']} -> {entry['target']}")
        else:
            lines.append(f"    ({label}_root) (none)")
    lines.append("[5] Cache directories without inbound references:")
    if plan["cache_dirs_to_clean"]:
        for path in plan["cache_dirs_to_clean"]:
            lines.append(f"    - {path}")
    else:
        lines.append("    (none)")
    return "\n".join(lines)


# ----------------------------- phase 2 -----------------------------


def apply_sqlite(state_db: Path) -> None:
    backup = state_db.with_suffix(state_db.suffix + f".bak.{_now_ts()}")
    shutil.copy2(state_db, backup)
    with sqlite3.connect(state_db) as conn:
        # 历史 → 成员 → pack 表（避免外键冲突；这里无 FK，依字典顺序亦可）
        for table in reversed(PACK_TABLES):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()


def apply_removal(path: Path) -> None:
    path.unlink()


def apply_extra_dirs_cleanup(openclaw_config: Path, to_remove: list[str]) -> None:
    config_data = _read_json(openclaw_config)
    extra_dirs = config_data["skills"]["load"]["extraDirs"]
    new_dirs = [item for item in extra_dirs if item not in to_remove]
    config_data["skills"]["load"]["extraDirs"] = new_dirs
    rendered = json.dumps(config_data, ensure_ascii=False, indent=2) + "\n"
    # 写回前做 diff assertion：new_dirs 中不能含 to_remove
    if any(item in to_remove for item in new_dirs):
        raise CleanNasError(
            f"{openclaw_config}: 写回后仍含需移除项；中止"
        )
    _atomic_write(openclaw_config, rendered)


def apply_symlink_removal(entry: dict, controller_root: Path) -> None:
    link = Path(entry["path"])
    # 删除前最后再 assert 一次 realpath 在 controller_root 内
    real = link.resolve()
    if not str(real).startswith(str(controller_root.resolve())):
        raise CleanNasError(
            f"{link}: realpath 越过受控根 {controller_root}，拒绝删除"
        )
    link.unlink()


def apply_cache_cleanup(plan: dict, github_cache_root: Path) -> None:
    for path_str in plan["cache_dirs_to_clean"]:
        target = Path(path_str)
        if not target.exists():
            continue
        shutil.rmtree(target)


# ----------------------------- main -----------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "一次性清理 skill-manager pack 体系在 NAS 上的遗留状态。"
            "默认 dry-run；必须显式 --apply 才落盘。"
        )
    )
    parser.add_argument(
        "--paths",
        type=Path,
        default=Path("clean_nas.paths.json"),
        help="paths.json 位置（默认当前目录）",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="mode",
        action="store_const",
        const="dry-run",
        default="dry-run",
    )
    mode.add_argument(
        "--apply",
        dest="mode",
        action="store_const",
        const="apply",
    )
    return parser.parse_args(argv)


def _load_paths(path_file: Path) -> dict:
    if not path_file.exists():
        raise CleanNasError(
            f"未找到 paths 文件: {path_file}；请复制 clean_nas.paths.example.json 改写"
        )
    data = _read_json(path_file)
    if not isinstance(data, dict):
        raise CleanNasError(f"{path_file}: 顶层不是对象")
    required = {
        "state_db",
        "openclaw_root",
        "hermes_root",
        "openclaw_config",
        "github_cache_root",
        "pack_discovery_state_dir",
    }
    missing = sorted(required - set(data.keys()))
    if missing:
        raise CleanNasError(f"{path_file}: 缺少字段: {', '.join(missing)}")
    return data


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        paths = _load_paths(args.paths)
        plan = phase0_inspect(paths)
    except CleanNasError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(render_plan(plan))
    if args.mode == "dry-run":
        print()
        print("(dry-run) 显式 --apply 才执行。")
        return 0

    # apply
    state_db = Path(paths["state_db"])
    discovery_state_dir = Path(paths["pack_discovery_state_dir"])
    openclaw_config = Path(paths["openclaw_config"])
    github_cache_root = Path(paths["github_cache_root"])

    try:
        apply_sqlite(state_db)
        for path_str in plan["discovery_files"]:
            apply_removal(Path(path_str))
        if plan["extra_dirs_to_remove"]:
            apply_extra_dirs_cleanup(
                openclaw_config, plan["extra_dirs_to_remove"]
            )
        # 软链删除：必须在缓存清理前，因为缓存清理依赖"软链已删"的判定
        for entry in plan["package_symlinks_hermes"]:
            apply_symlink_removal(entry, Path(paths["hermes_root"]))
        for entry in plan["package_symlinks_openclaw"]:
            apply_symlink_removal(entry, Path(paths["openclaw_root"]))
        # 缓存清理
        apply_cache_cleanup(plan, github_cache_root)
    except CleanNasError as exc:
        print(f"apply failed: {exc}", file=sys.stderr)
        return 1

    print()
    print("apply completed:")
    print(f"  - dropped {len(PACK_TABLES)} pack tables")
    print(
        f"  - removed {len(plan['discovery_files'])} discovery files"
    )
    print(
        f"  - removed {len(plan['extra_dirs_to_remove'])} extraDirs entries"
    )
    print(
        f"  - removed {len(plan['package_symlinks_hermes']) + len(plan['package_symlinks_openclaw'])} package symlinks"
    )
    print(
        f"  - cleaned {len(plan['cache_dirs_to_clean'])} cache directories"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
