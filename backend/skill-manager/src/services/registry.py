"""登记真源服务（SQLite registry_skill 表）与 registry.json 一次性导入。

RegistryService 是登记真源（skill-manager 自己的 SQLite）的唯一读写入口：

- 登记与删除不产生任何 git 子进程调用，也不读写 Skills 源库的
  registry.json（该文件归源库 sync 工具链，见 NAS 部署文档）；
- 本地 Skill path resolve 后必须位于源库根内且目录含 `SKILL.md`，
  穿越源库根时报错信息包含 "source root"；
- 拒绝 github repository+path 组合重复（同 id 视为更新，排除自身）；
- tags 排序去重。

`import_registry_json_if_empty()` 做一次性单向迁移：registry_skill 表为空
且源库 registry.json 存在时全部导入；表非空则跳过（绝不重复导入）；
全程只读该文件，绝不回写。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import ValidationError

from src.db import SkillStateStore
from src.models import RegistryFile, RegistrySkill, SKILL_ID_PATTERN, SkillSource

REGISTRY_FILENAME = "registry.json"

_ID_RE = re.compile(SKILL_ID_PATTERN)

# 本地发现时按目录名排除的项（隐藏目录统一按 "." 前缀排除，无需逐个列出）
_DISCOVERY_EXCLUDED_DIRS = {"scripts", "__pycache__", "node_modules", "logs", "output"}


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

    # ---------- 本地发现 ----------

    def discover_local(self) -> list[RegistrySkill]:
        """扫描源库根下含 `SKILL.md` 的目录，返回候选 RegistrySkill。

        跳过隐藏目录（"." 前缀）、工具/缓存目录；目录名不符合
        SkillId pattern 的候选同样跳过（发现阶段不作为错误中断）。
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
            candidates.append(
                RegistrySkill(
                    id=skill_id,
                    name=skill_id,
                    source=SkillSource.LOCAL,
                    path=skill_dir.relative_to(self.source_root).as_posix(),
                )
            )
        candidates.sort(key=lambda skill: skill.path)
        return candidates

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


def import_registry_json_if_empty(store: SkillStateStore, source_root: Path) -> int:
    """一次性迁移：registry_skill 表为空时导入源库 registry.json 全部条目。

    表非空 → 返回 0（单向迁移，绝不重复导入、绝不回写文件）；
    表空且文件不存在 → 返回 0；
    表空且文件损坏 → 抛 RegistryValidationError（消息含文件路径与原因），
    让应用启动失败而非静默丢失登记清单。
    """
    if store.count_registry_skills() > 0:
        return 0
    registry_path = source_root / REGISTRY_FILENAME
    if not registry_path.is_file():
        return 0
    try:
        registry = RegistryFile.model_validate(
            json.loads(registry_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise RegistryValidationError(
            f"invalid {registry_path}: {exc}"
        ) from exc
    for skill in registry.skills:
        # 与旧版 load() 行为一致：导入条目同样做 tags 排序去重（PRD R5）
        store.upsert_registry_skill(
            skill.model_copy(update={"tags": sorted(set(skill.tags))})
        )
    return len(registry.skills)
