"""唯一 Pydantic 契约来源：注册表模型与共享枚举（design 3.1）。

后续任务的发布计划、API 请求/响应模型也在此文件追加，禁止散落定义。
"""

from enum import StrEnum
from pathlib import Path
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
    """SQLite 登记表 `registry_skill` 单条目。

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


class PublishItem(BaseModel):
    """单次发布输入（Publisher 服务层内部对象）。

    `source` 由服务端从注册表/缓存解析；Task 5 的 API 请求模型不得接受
    调用方传入文件系统路径（R5）。
    """

    skill_id: SkillId
    target: TargetKey
    source: Path
    revision: str = ""


class PublishResultItem(BaseModel):
    """单项发布/回滚结果；批量接口以逐项结果表达部分成功（design 7）。"""

    skill_id: str
    target: TargetKey
    status: Literal["success", "blocked", "error"]
    action: Literal["add", "update", "none"] = "none"
    error: str = ""


class PublishBatchResult(BaseModel):
    items: list[PublishResultItem] = []


class ScanCandidate(BaseModel):
    """`POST /api/skills/github/scan` 返回的候选 Skill 目录。

    `path` 是仓库内相对 posix 路径（仓库根为 "."）；是否登记由管理员决定。
    """

    path: Annotated[str, Field(min_length=1)]


class UpdateInfo(BaseModel):
    """`POST /api/skills/check-updates` 的单项结果（design 3.2 github_check）。

    只反映检查时点的快照：远端 HEAD/tags、本地缓存 revision 与二者差异；
    检查动作本身不 fetch/clone、不变更缓存内容（R3）。
    """

    skill_id: str
    repository: str
    remote_revision: str
    remote_tags: list[str] = []
    cached_revision: str = ""
    has_update: bool = False
    checked_at: str


# ---------- API 请求/响应契约（design 7 / Task 5） ----------
# 密码只出现在请求体中，服务端常量时间比较后立即丢弃（R5）；
# 带密码模型与公开 plan 模型分开定义。


class AdminPasswordRequest(BaseModel):
    """仅含密码的写操作请求体（回滚、下架）。"""

    password: str


class ScanRequest(BaseModel):
    """`POST /api/skills/github/scan`：临时 clone 扫描候选目录。"""

    repository: str


class ScanResponse(BaseModel):
    repository: str
    candidates: list[ScanCandidate] = []


class RegisterGithubSkillRequest(BaseModel):
    """`POST /api/skills/github`：登记管理员选定的候选目录。

    skill id 由服务端从仓库与路径派生（design 3.1），不接受调用方指定。
    """

    password: str
    repository: str
    path: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    tags: list[Tag] = []
    summary: str = ""


class CheckUpdatesRequest(BaseModel):
    """`POST /api/skills/check-updates`：空列表表示全部 GitHub Skill。"""

    skill_ids: list[SkillId] = []


class UpdateCheckItem(BaseModel):
    """更新检查逐项结果：单项失败不中断其余项。"""

    skill_id: str
    result: Literal["ok", "error"]
    info: UpdateInfo | None = None
    error: str = ""


class UpdateCheckResponse(BaseModel):
    items: list[UpdateCheckItem] = []


class TargetDeployment(BaseModel):
    """`GET /api/skills` 卡片内单个 target 的部署状态。"""

    status: str
    revision: str = ""
    published_at: str = ""
    link_target: str = ""
    # 账实核对：账本 active 但目标链接不存在；真实动作以计划预览目录扫描为准
    link_missing: bool = False


class SkillCard(BaseModel):
    """左栏 Skill 卡片：筛选所需全部字段 + 双 target 状态 + 更新标记。"""

    id: SkillId
    name: str
    source: SkillSource
    path: str
    repository: str | None = None
    tags: list[str] = []
    summary: str = ""
    status: str = "active"
    deployments: dict[str, TargetDeployment] = {}
    update: UpdateInfo | None = None
    # 本环境 GitHub 缓存目录缺失（local 来源恒 False）；True 时前端禁用
    # 发布入口，引导先调 POST /api/skills/github/{id}/clone 重建缓存
    cache_missing: bool = False
    # 本环境源库中登记目录缺失（github 来源恒 False）；True 时前端提示
    # 源缺失并禁用发布入口，登记条目本身保留（不自动删除）
    source_missing: bool = False


class SkillListResponse(BaseModel):
    items: list[SkillCard] = []


class QueueItemRequest(BaseModel):
    """右栏发布队列单项：skill + 选定目标（OpenClaw/Hermes/两者）。"""

    skill_id: SkillId
    targets: Annotated[list[TargetKey], Field(min_length=1)]


class PublishPlanRequest(BaseModel):
    """`POST /api/skills/publish/plan`：只读预览，绝不变更文件系统。"""

    items: list[QueueItemRequest] = []


class PublishRequest(PublishPlanRequest):
    """`POST /api/skills/publish`：与 plan 相同的 items + 管理密码。"""

    password: str


PlanAction = Literal["add", "update", "unchanged", "blocked"]


class PlanItem(BaseModel):
    """发布计划单项：action 分类与原因（design 4.2）。"""

    skill_id: str
    target: TargetKey
    action: PlanAction
    reason: str = ""
    current_revision: str = ""
    planned_revision: str = ""


class PlanResponse(BaseModel):
    items: list[PlanItem] = []


class UnpublishResponse(BaseModel):
    skill_id: str
    target: TargetKey
    status: Literal["removed"] = "removed"


class UpdateSkillTagsRequest(BaseModel):
    """`PATCH /api/skills/{skill_id}/tags`：单卡标签全量替换（密码保护）。

    标签维护不依赖源目录存在（源缺失条目同样可编辑），路径校验在
    RegistryService.update_skill_tags 中刻意绕过（见其 docstring）。
    """

    password: str
    tags: list[Tag] = []


class UpdateSkillTagsResponse(BaseModel):
    skill_id: SkillId
    tags: list[str] = []


class DeleteSkillResponse(BaseModel):
    """`DELETE /api/skills/{skill_id}`：删除已登记 GitHub Skill。"""

    skill_id: str
