"""Task 7 NAS 部署链路静态断言。

直接读取仓库内部署文件文本，验证 Compose 挂载边界、Nginx 路由与
部署脚本映射；不启动容器，纯静态检查。
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = REPO_ROOT / "docker-compose.nas.yml"
SKILL_COMPOSE_FILE = REPO_ROOT / "docker-compose.skill-manager.nas.yml"
NGINX_CONF = REPO_ROOT / "nginx" / "web.conf"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy-nas.sh"

# skill-manager-backend 允许的完整挂载清单（design 2.2 / R6：仅五类目录）
BACKEND_ALLOWED_MOUNTS = {
    "${SKILLS_SOURCE_HOST_PATH}:/mnt/skills-source:rw",
    "${GITHUB_SKILL_CACHE_HOST_PATH}:/mnt/github-skill-cache:rw",
    "${OPENCLAW_SKILLS_HOST_PATH}:/mnt/targets/openclaw:rw",
    "${HERMES_SKILLS_HOST_PATH}:/mnt/targets/hermes:rw",
    "skill-manager-state:/app/state",
}


@pytest.fixture(scope="module")
def compose_text() -> str:
    assert COMPOSE_FILE.exists(), f"missing {COMPOSE_FILE}"
    return COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def nginx_text() -> str:
    assert NGINX_CONF.exists(), f"missing {NGINX_CONF}"
    return NGINX_CONF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_compose_text() -> str:
    assert SKILL_COMPOSE_FILE.exists(), f"missing {SKILL_COMPOSE_FILE}"
    return SKILL_COMPOSE_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def deploy_text() -> str:
    assert DEPLOY_SCRIPT.exists(), f"missing {DEPLOY_SCRIPT}"
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _service_section(compose_text: str, service: str) -> str:
    """提取 compose 中某个顶级服务的 YAML 段落（到下一个同级键为止）。"""
    lines = compose_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == f"  {service}:":
            start = i
            break
    assert start is not None, f"service '{service}' not found in compose file"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        top_level_key = line and not line.startswith(" ") and line.rstrip().endswith(":")
        sibling_service = (
            line.startswith("  ")
            and not line.startswith("   ")
            and line.rstrip().endswith(":")
        )
        if top_level_key or sibling_service:
            end = j
            break
    return "\n".join(lines[start:end])


def _volume_lines(section: str) -> list[str]:
    """提取服务段落中 volumes: 块内的挂载行（去掉缩进与 '- ' 前缀）。"""
    in_volumes = False
    result: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped == "volumes:":
            in_volumes = True
            continue
        if in_volumes:
            if stripped.startswith("- "):
                result.append(stripped[2:])
            elif stripped:
                in_volumes = False
    return result


def test_base_compose_does_not_define_skill_manager(compose_text: str):
    # 回归守护：compose 的变量插值与卷规格校验是全文件的，skill-manager 的
    # 必填 .env 变量若进入基础文件，会卡住其他 target 的 build/up。
    # 服务定义只允许存在于 overlay 文件（docker-compose.skill-manager.nas.yml）。
    # 匹配带两格缩进的服务/卷定义键，避免误伤注释里的 upstream 名称
    assert "\n  skill-manager-backend:" not in compose_text
    assert "\n  skill-manager-frontend:" not in compose_text
    assert "\n  skill-manager-state:" not in compose_text


def test_compose_exposes_only_fixed_skill_manager_mounts(
    compose_text: str, skill_compose_text: str
):
    # 红线：任何部署文件都不得挂 docker.sock
    assert "/var/run/docker.sock" not in compose_text
    assert "/var/run/docker.sock" not in skill_compose_text
    assert "${SKILLS_SOURCE_HOST_PATH}:" in skill_compose_text
    assert "${GITHUB_SKILL_CACHE_HOST_PATH}:" in skill_compose_text
    assert "${OPENCLAW_SKILLS_HOST_PATH}:" in skill_compose_text
    assert "${HERMES_SKILLS_HOST_PATH}:" in skill_compose_text


def test_compose_backend_has_no_unrelated_mounts(skill_compose_text: str):
    section = _service_section(skill_compose_text, "skill-manager-backend")
    assert set(_volume_lines(section)) == BACKEND_ALLOWED_MOUNTS


def test_compose_defines_skill_manager_services_and_state_volume(
    skill_compose_text: str,
):
    assert _service_section(skill_compose_text, "skill-manager-backend")
    assert _service_section(skill_compose_text, "skill-manager-frontend")
    assert "skill-manager-state:" in skill_compose_text
    # 前端走 127.0.0.1 本地端口映射，与其他前端服务一致
    assert '"127.0.0.1:3008:3008"' in skill_compose_text
    # 后端仅在内部网络暴露 8097
    assert '"8097"' in skill_compose_text


def test_compose_admin_password_only_reaches_backend(
    skill_compose_text: str,
):
    backend = _service_section(skill_compose_text, "skill-manager-backend")
    frontend = _service_section(skill_compose_text, "skill-manager-frontend")
    assert "SKILL_MANAGER_ADMIN_PASSWORD" in backend
    assert "SKILL_MANAGER_ADMIN_PASSWORD" not in frontend


def test_nginx_routes_skill_manager(nginx_text: str):
    # 两个 upstream
    assert "server skill-manager-backend:8097" in nginx_text
    assert "server skill-manager-frontend:3008" in nginx_text
    # 三件路由：静态资源、页面、API
    assert "location /skills/_next/static/" in nginx_text
    assert "location /skills" in nginx_text
    assert "location /api/skills/" in nginx_text
    # 静态资源走长缓存
    skills_static_block = nginx_text.split("location /skills/_next/static/")[1]
    assert "immutable" in skills_static_block
    # API 原样转发（后端路由本身是 /api/skills 前缀，不剥前缀）
    api_block = nginx_text.split("location /api/skills/")[1]
    assert "proxy_pass http://skill_manager_backend;" in api_block
    assert "rewrite ^/api/skills/" not in api_block
    # 根聚合页有 /skills 导航链接
    assert 'href="/skills/"' in nginx_text


def test_deploy_script_maps_skill_manager(deploy_text: str):
    # target 校验与 get_services 分支
    assert "fund-select|housing-map|skill-manager" in deploy_text
    # all 组包含两个服务
    assert "skill-manager-backend skill-manager-frontend" in deploy_text
    # buildx 配置
    assert (
        'skill-manager-frontend) echo "apps/skill-manager:apps/skill-manager/Dockerfile:skill-manager-frontend"'
        in deploy_text
    )
    # skill-manager compose 定义独立成 overlay 文件，脚本按 target 条件叠加
    assert "docker-compose.skill-manager.nas.yml" in deploy_text
    # 帮助文本 target 列表
    assert "skill-manager" in deploy_text


def test_skill_manager_frontend_dockerfile_exists():
    dockerfile = REPO_ROOT / "apps" / "skill-manager" / "Dockerfile"
    assert dockerfile.exists(), "前端镜像构建需要 apps/skill-manager/Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    # standalone 惯例 + 端口 3008
    assert ".next/standalone" in text
    assert "3008" in text
    # 红线：前端镜像不接收管理密码（ARG/ENV 均禁止；注释提及变量名无妨）
    assert "ARG SKILL_MANAGER_ADMIN_PASSWORD" not in text
    assert "ENV SKILL_MANAGER_ADMIN_PASSWORD" not in text
