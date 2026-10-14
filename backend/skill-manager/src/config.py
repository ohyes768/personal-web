"""受限 NAS 路径与管理配置（design 2.2 固定环境配置）。

后端只从环境变量读取挂载根与管理密码；路径在进程启动时 resolve、
要求目录存在。targets_mount_root 可选：设置时要求两个 target 根位于
其内（本地 dev 脚本路径）；未设置时跳过包含关系校验，容器内外的
边界由部署层 bind mount 白名单保证（NAS 同路径挂载部署）。
"""

from pathlib import Path
from src.models import InstallTargetConfig

from pydantic import AliasChoices, Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 需要存在性校验并 resolve 的必填挂载根字段
# （targets_mount_root 可选：非 None 时才 resolve + 存在性 + containment 校验）
_MOUNT_ROOT_FIELDS = (
    "skills_source_root",
    "github_skill_cache_root",
    "state_dir",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True, env_ignore_empty=True)

    _legacy_hermes_root: Path | None = PrivateAttr(default=None)

    skills_source_root: Path
    github_skill_cache_root: Path
    hermes_skills_root: Path | None = None
    hermes_profiles_root: Path | None = Field(default=None, validation_alias=AliasChoices("SKILL_MANAGER_HERMES_PROFILES_ROOT", "hermes_profiles_root"))
    hermes_targets: list[InstallTargetConfig] | None = Field(default=None, validation_alias=AliasChoices("SKILL_MANAGER_HERMES_TARGETS", "hermes_targets"))
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
        if self.hermes_targets is None:
            if self.hermes_skills_root is None:
                raise ValueError("HERMES_SKILLS_ROOT or SKILL_MANAGER_HERMES_TARGETS is required")
            self.hermes_targets = [InstallTargetConfig(id="hermes", name="默认环境", profile_name="default", skills_root=self.hermes_skills_root)]
        if not self.hermes_targets:
            raise ValueError("Hermes targets cannot be empty")
        roots, ids = [], set()
        for target in self.hermes_targets:
            if target.id in ids:
                raise ValueError("duplicate Hermes target ID")
            ids.add(target.id)
            if not target.skills_root.is_absolute():
                raise ValueError("Hermes target root must be absolute")
            resolved = target.skills_root.resolve()
            if any(resolved.is_relative_to(other) or other.is_relative_to(resolved) for other in roots):
                raise ValueError("Hermes target roots cannot overlap")
            if any(resolved.is_relative_to(getattr(self, name)) or getattr(self, name).is_relative_to(resolved) for name in _MOUNT_ROOT_FIELDS):
                raise ValueError("Hermes target root overlaps a source, cache or state root")
            if self.targets_mount_root and not resolved.is_relative_to(self.targets_mount_root):
                raise ValueError("target root must be inside targets_mount_root")
            # Preserve configured path to detect later symlink redirection.
            target.skills_root = target.skills_root.absolute()
            roots.append(resolved)
        if self.hermes_profiles_root is not None:
            if not self.hermes_profiles_root.is_absolute():
                raise ValueError("profiles root must be absolute")
            resolved = self.hermes_profiles_root.resolve()
            if any(resolved.is_relative_to(getattr(self, name)) or getattr(self, name).is_relative_to(resolved) for name in _MOUNT_ROOT_FIELDS):
                raise ValueError("profiles root overlaps source, cache or state")
            if self.targets_mount_root and not resolved.is_relative_to(self.targets_mount_root):
                raise ValueError("profiles root must be inside targets_mount_root")
            if any(t.id == 'hermes' and (resolved.is_relative_to(t.skills_root.resolve()) or t.skills_root.resolve().is_relative_to(resolved)) for t in self.hermes_targets):
                raise ValueError("default skills root overlaps profiles root")
            self.hermes_profiles_root = self.hermes_profiles_root.absolute()
        self._legacy_hermes_root = self.hermes_skills_root
        default = next((t for t in self.hermes_targets if t.id == "hermes"), None)
        self.hermes_skills_root = default.skills_root if default else None
        return self
