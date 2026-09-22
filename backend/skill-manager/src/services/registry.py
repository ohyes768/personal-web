"""登记真源服务（SQLite registry_skill 表）。

RegistryService 是登记真源（skill-manager 自己的 SQLite）的唯一读写入口：

- 登记与删除不产生任何 git 子进程调用，也不读写 Skills 源库的任何
  登记文件（源库 sync 工具链的 registry.json 与 skill-manager 无关）；
- 本地 Skill path resolve 后必须位于源库根内且目录含 `SKILL.md`，
  穿越源库根时报错信息包含 "source root"；
- 拒绝 github repository+path 组合重复（同 id 视为更新，排除自身）；
- tags 排序去重；
- `sync_local()` 把源库目录对账进登记表：仅登记新出现的自研 skill，
  name/summary 取自 SKILL.md frontmatter（缺失降级），已登记条目与
  源缺失条目一律不动。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.db import SkillStateStore
from src.models import RegistrySkill, SKILL_ID_PATTERN, SkillSource

_ID_RE = re.compile(SKILL_ID_PATTERN)

# 本地发现时按目录名排除的项（隐藏目录统一按 "." 前缀排除，无需逐个列出）
_DISCOVERY_EXCLUDED_DIRS = {"scripts", "__pycache__", "node_modules", "logs", "output"}

# frontmatter 只取文件头，防超大 SKILL.md 拖慢扫描
_FRONTMATTER_READ_BYTES = 4096


def _parse_skill_md_frontmatter(path: Path) -> dict[str, str]:
    """解析 SKILL.md 头部 YAML frontmatter 的 name/description。

    只识别文件第一行为 `---` 的围栏块内 `key: value` 单行标量（name/
    description 均为标量，无需完整 YAML 依赖）；无围栏、字段缺失或读取
    失败一律返回空 dict，调用方降级（name 退回目录 id、summary 留空）。
    """
    try:
        head = path.read_bytes()[: _FRONTMATTER_READ_BYTES].decode(
            "utf-8", errors="replace"
        )
    except OSError:
        return {}
    if not head.startswith("---"):
        return {}
    meta: dict[str, str] = {}
    for line in head.splitlines()[1:]:
        stripped = line.strip()
        if stripped == "---":
            break
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        if key.strip().lower() in ("name", "description"):
            meta[key.strip().lower()] = value.strip()
    return meta


class RegistryValidationError(ValueError):
    """登记操作未通过校验，或操作的 skill id 不存在。"""


class RegistryService:
    """以 registry_skill 表为真源、`source_root` 为路径边界的登记服务。"""

    def __init__(self, store: SkillStateStore, source_root: Path) -> None:
        self.store = store
        self.source_root = source_root.resolve()

    # ---------- 读取 ----------

    def list_skills(self) -> list[RegistrySkill]:
        return self.store.list_registry_skills()

    def get(self, skill_id: str) -> RegistrySkill | None:
        return self.store.get_registry_skill(skill_id)

    # ---------- 写入 ----------

    def upsert(self, skill: RegistrySkill) -> None:
        """校验并写入单个条目（同 id 替换）。"""
        normalized = self._validated(skill)
        self._reject_duplicate_repo_path(normalized)
        self.store.upsert_registry_skill(normalized)

    def remove(self, skill_id: str) -> None:
        """移除单个条目；id 不存在时报错。"""
        if not self.store.delete_registry_skill(skill_id):
            raise RegistryValidationError(f"unknown skill id: {skill_id}")

    # ---------- 本地发现与对账 ----------

    def discover_local(self) -> list[RegistrySkill]:
        """扫描源库根下含 `SKILL.md` 的目录，返回候选 RegistrySkill。

        跳过隐藏目录（"." 前缀）、工具/缓存目录；目录名不符合
        SkillId pattern 的候选同样跳过（发现阶段不作为错误中断）。
        候选的 name/summary 取自 SKILL.md frontmatter（缺失时降级，见
        `_parse_skill_md_frontmatter`）。
        """
        candidates: list[RegistrySkill] = []
        for dirpath, dirnames, filenames in os.walk(self.source_root):
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(".") and d not in _DISCOVERY_EXCLUDED_DIRS
            ]
            if "SKILL.md" not in filenames:
                continue
            skill_dir = Path(dirpath)
            skill_id = skill_dir.name
            if not _ID_RE.match(skill_id):
                continue
            meta = _parse_skill_md_frontmatter(skill_dir / "SKILL.md")
            candidates.append(
                RegistrySkill(
                    id=skill_id,
                    name=meta.get("name") or skill_id,
                    source=SkillSource.LOCAL,
                    path=skill_dir.relative_to(self.source_root).as_posix(),
                    summary=meta.get("description", ""),
                )
            )
        candidates.sort(key=lambda skill: skill.path)
        return candidates

    def sync_local(self) -> int:
        """把源库目录与登记表对账：仅登记新出现的自研 skill，返回新增数。

        已登记条目一律不动（绝不覆盖人工维护的 summary/tags/status）；
        目录缺失的已登记条目不处理（保留，卡片以 source_missing 提示）。
        源库根不可达时 os.walk 静默返回空，对账为 no-op（调用方降级）。
        """
        discovered = {skill.id: skill for skill in self.discover_local()}
        existing_local = {
            skill.id
            for skill in self.list_skills()
            if skill.source is SkillSource.LOCAL
        }
        new_ids = sorted(discovered.keys() - existing_local)
        for skill_id in new_ids:
            self.store.upsert_registry_skill(discovered[skill_id])
        return len(new_ids)

    # ---------- 内部工具 ----------

    def _validated(self, skill: RegistrySkill) -> RegistrySkill:
        """返回 tags 排序去重后的新对象，并校验路径边界。"""
        normalized = skill.model_copy(update={"tags": sorted(set(skill.tags))})
        self._check_path(normalized)
        return normalized

    def _check_path(self, skill: RegistrySkill) -> None:
        if skill.source is SkillSource.LOCAL:
            resolved = (self.source_root / skill.path).resolve()
            if not resolved.is_relative_to(self.source_root):
                raise RegistryValidationError(
                    f"local skill path {skill.path!r} escapes the source root "
                    f"({self.source_root})"
                )
            if not (resolved / "SKILL.md").is_file():
                raise RegistryValidationError(
                    f"local skill dir {skill.path!r} does not contain SKILL.md"
                )
            return
        # github skill 的 path 是仓库内相对目录（可为 "."），缓存校验在发布时进行
        relative = Path(skill.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise RegistryValidationError(
                f"github skill path {skill.path!r} must be a relative subdirectory"
            )

    def _reject_duplicate_repo_path(self, skill: RegistrySkill) -> None:
        """github repository+path 组合唯一；同 id 视为更新，排除自身。"""
        if skill.source is not SkillSource.GITHUB:
            return
        key = (str(skill.repository), skill.path)
        for other in self.store.list_registry_skills():
            if other.id == skill.id or other.source is not SkillSource.GITHUB:
                continue
            if (str(other.repository), other.path) == key:
                raise RegistryValidationError(
                    f"duplicate github repository+path: {key}"
                )

