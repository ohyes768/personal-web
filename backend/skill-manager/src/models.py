"""唯一 Pydantic 契约来源：注册表模型与共享枚举（design 3.1）。

后续任务的发布计划、API 请求/响应模型也在此文件追加，禁止散落定义。
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

# discover_local 等非 Pydantic 场景复用同一 pattern，避免两处正则漂移
SKILL_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"
SkillId = Annotated[str, Field(pattern=SKILL_ID_PATTERN)]
Tag = Annotated[str, Field(min_length=1, max_length=40)]


class SkillSource(StrEnum):
    LOCAL = "local"
    GITHUB = "github"


class TargetKey(StrEnum):
    OPENCLAW = "openclaw"
    HERMES = "hermes"


class RegistrySkill(BaseModel):
    """`registry.json` 单条目。

    - `source=local`：`path` 是源库内相对目录，必须含 `SKILL.md`（目录级校验在 RegistryService）。
    - `source=github`：`repository` 必填，`path` 是仓库内相对目录，可为 `.`。
    - 去重/排序 tags 与路径穿越拒绝由 RegistryService 负责，模型只守字段契约。
    """

    id: SkillId
    name: Annotated[str, Field(min_length=1)]
    source: SkillSource
    path: Annotated[str, Field(min_length=1)]
    repository: HttpUrl | None = None
    tags: list[Tag] = []
    summary: str = ""
    status: Literal["active", "deprecated"] = "active"
    # 编排型 skill 的依赖清单（skill id 列表）；design 3.1 之外的可选扩展字段
    depends_on: list[SkillId] = []

    @model_validator(mode="after")
    def _validate_source_specific_fields(self) -> "RegistrySkill":
        if self.source is SkillSource.GITHUB and self.repository is None:
            raise ValueError("github skill requires repository")
        if self.source is SkillSource.LOCAL and self.repository is not None:
            raise ValueError("local skill must not carry repository")
        return self


class RegistryAgent(BaseModel):
    """`registry.json` 顶层 `agents` 对象的单个 agent 分配。

    只保存 description 与分配的 skill id 列表；机器本地的 skills_dir、
    enabled 等目标配置不进注册表（由 sync-config.json / NAS 部署配置提供）。
    """

    description: str = ""
    skills: list[SkillId] = []


class RegistryFile(BaseModel):
    """`registry.json` 顶层结构：skill 清单 + 显式 agent 分配。"""

    version: str = "1.0"
    updated: str = ""
    skills: list[RegistrySkill] = []
    agents: dict[str, RegistryAgent] = {}
