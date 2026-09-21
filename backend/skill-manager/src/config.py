"""受限 NAS 路径与管理配置（design 2.2 固定环境配置）。

后端只从环境变量读取挂载根与管理密码；路径在进程启动时 resolve、
要求目录存在。targets_mount_root 可选：设置时要求两个 target 根位于
其内（本地 dev 脚本路径）；未设置时跳过包含关系校验，容器内外的
边界由部署层 bind mount 白名单保证（NAS 同路径挂载部署）。
"""

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 需要存在性校验并 resolve 的必填挂载根字段
# （targets_mount_root 可选：非 None 时才 resolve + 存在性 + containment 校验）
_MOUNT_ROOT_FIELDS = (
    "skills_source_root",
    "github_skill_cache_root",
    "openclaw_skills_root",
    "hermes_skills_root",
    "state_dir",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    skills_source_root: Path
    github_skill_cache_root: Path
    openclaw_skills_root: Path
    hermes_skills_root: Path
    state_dir: Path = Field(
        validation_alias=AliasChoices("SKILL_MANAGER_STATE_DIR", "state_dir")
    )
    admin_password: SecretStr = Field(
        validation_alias=AliasChoices("SKILL_MANAGER_ADMIN_PASSWORD", "admin_password")
    )
    service_port: int = Field(
        default=8097,
        validation_alias=AliasChoices("SKILL_MANAGER_SERVICE_PORT", "service_port"),
    )
    targets_mount_root: Path | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "targets_mount_root", "SKILL_MANAGER_TARGETS_MOUNT_ROOT"
        ),
    )

    @model_validator(mode="after")
    def _validate_mounted_roots(self) -> "Settings":
        """resolve 每个根路径、要求目录存在；targets_mount_root 设置时
        另行限定 target 根的挂载边界（未设置则边界由部署层 bind mount
        白名单保证，见 NAS 同路径挂载部署）。"""
        if not self.admin_password.get_secret_value():
            raise ValueError(
                "SKILL_MANAGER_ADMIN_PASSWORD must be set to a non-empty value"
            )
        for field_name in _MOUNT_ROOT_FIELDS:
            resolved = getattr(self, field_name).resolve()
            if not resolved.is_dir():
                raise ValueError(
                    f"{field_name} must exist and be a directory: {resolved}"
                )
            setattr(self, field_name, resolved)

        if self.targets_mount_root is not None:
            resolved = self.targets_mount_root.resolve()
            if not resolved.is_dir():
                raise ValueError(
                    "targets_mount_root must exist and be a directory: "
                    f"{resolved}"
                )
            self.targets_mount_root = resolved
            for target_name in ("openclaw_skills_root", "hermes_skills_root"):
                target = getattr(self, target_name)
                if not target.is_relative_to(self.targets_mount_root):
                    raise ValueError(
                        f"target root {target_name} ({target}) must be inside "
                        f"targets_mount_root ({self.targets_mount_root})"
                    )
        return self
