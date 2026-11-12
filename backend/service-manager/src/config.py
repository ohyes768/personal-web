"""service-manager 配置（design §1 / §9）。

Settings 不在模块导入时实例化——import src.main 不应要求环境变量已就绪。
lifespan 在启动时构造 Settings；生产环境缺密码或签名密钥直接拒绝启动。
"""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True, env_ignore_empty=True)

    # ---- 身份（必需，缺失拒绝启动）----
    admin_password: SecretStr = Field(alias="SERVICE_MANAGER_ADMIN_PASSWORD")
    session_secret: SecretStr = Field(alias="SERVICE_MANAGER_SESSION_SECRET")
    public_origin: str = Field(
        default="http://localhost:3012", alias="SERVICE_MANAGER_PUBLIC_ORIGIN"
    )
    # 允许的额外同源写请求来源（逗号分隔）；默认只允许 public_origin
    allowed_origins: str = Field(default="", alias="SERVICE_MANAGER_ALLOWED_ORIGINS")

    # ---- 数据 ----
    data_dir: Path = Field(default=Path("./data"), alias="SERVICE_MANAGER_DATA_DIR")

    # ---- 分组 ----
    # 「我自己开发的」应用所在的 compose 项目（逗号分隔）。台账里属于这些
    # 项目的服务在列表里单独一个 tab，其余归「其他」。
    own_projects: str = Field(
        default="personal-web", alias="SERVICE_MANAGER_OWN_PROJECTS"
    )

    # ---- Docker ----
    # 经 socket proxy 的 HTTP 端点；空 = 不使用 Docker（台账仍可用）
    docker_host: str = Field(default="", alias="SERVICE_MANAGER_DOCKER_HOST")
    docker_timeout: float = Field(default=5.0, alias="SERVICE_MANAGER_DOCKER_TIMEOUT")

    # ---- GitHub ----
    github_token: SecretStr | None = Field(default=None, alias="SERVICE_MANAGER_GITHUB_TOKEN")

    # ---- cookie ----
    secure_cookie: bool = Field(default=True, alias="SERVICE_MANAGER_SECURE_COOKIE")
    cookie_path: str = Field(default="/api", alias="SERVICE_MANAGER_COOKIE_PATH")
    session_hours: int = Field(default=12, alias="SERVICE_MANAGER_SESSION_HOURS")

    # ---- 检查周期（秒）；0 = 该检查不自动跑 ----
    docker_interval: int = Field(default=60, alias="SERVICE_MANAGER_DOCKER_INTERVAL")
    url_interval: int = Field(default=300, alias="SERVICE_MANAGER_URL_INTERVAL")
    tls_interval: int = Field(default=43200, alias="SERVICE_MANAGER_TLS_INTERVAL")
    release_interval: int = Field(default=21600, alias="SERVICE_MANAGER_RELEASE_INTERVAL")
    # 后台调度循环是否启用（测试里关掉，避免线程干扰）
    scheduler_enabled: bool = Field(default=True, alias="SERVICE_MANAGER_SCHEDULER_ENABLED")

    service_port: int = Field(default=8102, alias="SERVICE_MANAGER_SERVICE_PORT")

    @field_validator("admin_password", "session_secret")
    @classmethod
    def _non_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("must be a non-empty value")
        return value

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        return value.expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_dir / "service-manager.sqlite3"

    @property
    def origin_allowlist(self) -> tuple[str, ...]:
        items = [self.public_origin.strip().rstrip("/")]
        for extra in self.allowed_origins.split(","):
            cleaned = extra.strip().rstrip("/")
            if cleaned:
                items.append(cleaned)
        return tuple(dict.fromkeys(items))

    @property
    def own_project_list(self) -> tuple[str, ...]:
        """自己开发的 compose 项目名（去重、去空）。"""
        items = [item.strip() for item in self.own_projects.split(",")]
        return tuple(dict.fromkeys(item for item in items if item))
