"""registry.json 的校验、原子写入与本地 Skill 发现（design 3.1）。

RegistryService 是 Skills 源库内 `registry.json` 的唯一写入者：

- 只加载 `registry.json`，不回读 HTML 或其他来源；
- 本地 Skill path resolve 后必须位于源库根内且目录含 `SKILL.md`，
  穿越源库根时报错信息包含 "source root"；
- 拒绝重复 id 与重复的 github repository+path 组合；
- tags 排序去重；
- 全部写入使用临时文件 + `os.replace` 原子替换；
- `commit_registry_change()` 只运行固定参数列表的
  `git add registry.json` 与 `git commit`（shell=False），
  不接受任何外部拼接的命令片段。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from pydantic import ValidationError

from src.models import RegistryFile, RegistrySkill, SKILL_ID_PATTERN, SkillSource

REGISTRY_FILENAME = "registry.json"
COMMIT_MESSAGE = "chore(registry): update registry.json"

_ID_RE = re.compile(SKILL_ID_PATTERN)

# 本地发现时按目录名排除的项（隐藏目录统一按 "." 前缀排除，无需逐个列出）
_DISCOVERY_EXCLUDED_DIRS = {"scripts", "__pycache__", "node_modules", "logs", "output"}


class RegistryValidationError(ValueError):
    """registry.json 内容或候选 Skill 目录未通过校验。"""


class RegistryService:
    """以 `source_root` 为边界的注册表读写服务。"""

    def __init__(self, source_root: Path) -> None:
        self.source_root = source_root.resolve()

    @property
    def registry_path(self) -> Path:
        return self.source_root / REGISTRY_FILENAME

    # ---------- 读取与校验 ----------

    def load(self) -> RegistryFile:
        if not self.registry_path.is_file():
            raise RegistryValidationError(f"registry not found: {self.registry_path}")
        try:
            registry = RegistryFile.model_validate(
                json.loads(self.registry_path.read_text(encoding="utf-8"))
            )
        except ValidationError as exc:
            raise RegistryValidationError(f"invalid {REGISTRY_FILENAME}: {exc}") from exc
        self._validate_unique(registry)
        validated = registry.model_copy(
            update={"skills": [self._validated(skill) for skill in registry.skills]}
        )
        return validated

    def upsert(self, skill: RegistrySkill) -> RegistryFile:
        """校验并写入单个条目（同 id 替换），保留 agents 与其他条目。"""
        normalized = self._validated(skill)
        registry = self._load_or_empty()
        skills = [s for s in registry.skills if s.id != normalized.id]
        skills.append(normalized)
        updated = registry.model_copy(update={"skills": skills})
        self._save(updated)
        return updated

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

    # ---------- 固定参数 git 提交 ----------

    def commit_registry_change(self) -> None:
        """只运行固定参数的 `git add registry.json` 与 `git commit`。

        命令为写死的列表参数（shell=False），消息为模块常量；
        不存在可由调用方注入的命令片段。
        """
        for argv in (
            ["git", "add", REGISTRY_FILENAME],
            ["git", "commit", "-m", COMMIT_MESSAGE],
        ):
            subprocess.run(
                argv,
                cwd=self.source_root,
                shell=False,
                check=True,
                capture_output=True,
            )

    # ---------- 内部工具 ----------

    def _load_or_empty(self) -> RegistryFile:
        if not self.registry_path.is_file():
            return RegistryFile()
        return self.load()

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

    @staticmethod
    def _validate_unique(registry: RegistryFile) -> None:
        seen_ids: set[str] = set()
        seen_repo_paths: set[tuple[str, str]] = set()
        for skill in registry.skills:
            if skill.id in seen_ids:
                raise RegistryValidationError(f"duplicate skill id: {skill.id}")
            seen_ids.add(skill.id)
            if skill.source is SkillSource.GITHUB:
                key = (str(skill.repository), skill.path)
                if key in seen_repo_paths:
                    raise RegistryValidationError(
                        f"duplicate github repository+path: {key}"
                    )
                seen_repo_paths.add(key)

    def _save(self, registry: RegistryFile) -> None:
        payload = (
            json.dumps(registry.model_dump(mode="json"), ensure_ascii=False, indent=2)
            + "\n"
        )
        tmp_path = self.registry_path.with_name(
            f"{REGISTRY_FILENAME}.{uuid.uuid4().hex}.tmp"
        )
        try:
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, self.registry_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
