"""受限 NAS 路径与管理配置（design 2.2 固定环境配置）。

后端只从环境变量读取挂载根与管理密码；路径在进程启动时 resolve、
要求目录存在，两个 target 根必须位于 targets_mount_root 之内。
"""

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 需要存在性校验并 resolve 的全部挂载根字段
_MOUNT_ROOT_FIELDS = (
    "skills_source_root",
    "github_skill_cache_root",
    "openclaw_skills_root",
    "hermes_skills_root",
    "state_dir",
    "targets_mount_root",
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
    targets_mount_root: Path = Field(
        validation_alias=AliasChoices(
            "targets_mount_root", "SKILL_MANAGER_TARGETS_MOUNT_ROOT"
        )
    )

    @model_validator(mode="after")
    def _validate_mounted_roots(self) -> "Settings":
        """resolve 每个根路径、要求目录存在，并限定 target 根的挂载边界。"""
        for field_name in _MOUNT_ROOT_FIELDS:
            resolved = getattr(self, field_name).resolve()
            if not resolved.is_dir():
                raise ValueError(
                    f"{field_name} must exist and be a directory: {resolved}"
                )
            setattr(self, field_name, resolved)

        for target_name in ("openclaw_skills_root", "hermes_skills_root"):
            target = getattr(self, target_name)
            if not target.is_relative_to(self.targets_mount_root):
                raise ValueError(
                    f"target root {target_name} ({target}) must be inside "
                    f"targets_mount_root ({self.targets_mount_root})"
                )
        return self
