"""唯一 Pydantic 契约来源：注册表模型与共享枚举（design 3.1）。

后续任务的发布计划、API 请求/响应模型也在此文件追加，禁止散落定义。
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

SkillId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")]
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

    @model_validator(mode="after")
    def _validate_source_specific_fields(self) -> "RegistrySkill":
        if self.source is SkillSource.GITHUB and self.repository is None:
            raise ValueError("github skill requires repository")
        if self.source is SkillSource.LOCAL and self.repository is not None:
            raise ValueError("local skill must not carry repository")
        return self
