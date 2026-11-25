"""Docker 元数据投影（A3 / A4 / A5 口径）。"""

from __future__ import annotations

from src.docker_reader import (
    compute_source_key,
    project_compose_files,
    project_container,
    project_ports,
)
from tests.conftest import container_payload


def test_source_key_uses_compose_labels() -> None:
    key, oneoff = compute_source_key(
        labels={
            "com.docker.compose.project": "personal-web",
            "com.docker.compose.service": "dividend-frontend",
            "com.docker.compose.container-number": "1",
        },
        container_id="abc",
    )
    assert key == "nas:compose:personal-web:dividend-frontend:1"
    assert oneoff is False


def test_source_key_defaults_number_to_one() -> None:
    key, _ = compute_source_key(
        labels={
            "com.docker.compose.project": "immich",
            "com.docker.compose.service": "immich-server",
        },
        container_id="abc",
    )
    assert key == "nas:compose:immich:immich-server:1"


def test_source_key_for_label_less_container() -> None:
    key, _ = source = compute_source_key(labels={}, container_id="deadbeefcafe1234")
    assert key == "nas:container:deadbeefcafe"


def test_oneoff_flag_detected() -> None:
    _, oneoff = compute_source_key(
        labels={
            "com.docker.compose.project": "task-web",
            "com.docker.compose.service": "task",
            "com.docker.compose.oneoff": "True",
        },
        container_id="abc",
    )
    assert oneoff is True


def test_rebuild_keeps_same_source_key() -> None:
    labels = {
        "com.docker.compose.project": "p",
        "com.docker.compose.service": "s",
        "com.docker.compose.container-number": "1",
    }
    first, _ = compute_source_key(labels=labels, container_id="a" * 64)
    second, _ = compute_source_key(labels=labels, container_id="b" * 64)
    assert first == second


def test_published_ports_projected() -> None:
    views = project_ports(
        ports_payload={
            "3003/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3003"}],
            "8101/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8101"}],
        },
        state="running",
        network_mode="bridge",
    )
    assert len(views) == 2
    by_port = {view.host_port: view for view in views}
    assert by_port[3003].kind == "published"
    assert by_port[3003].address_family == "ipv4"
    assert by_port[8101].container_port == 8101


def test_exposed_only_port_is_not_host_port() -> None:
    views = project_ports(
        ports_payload={"8097/tcp": None, "8097/tcp ": None},
        state="running",
        network_mode="bridge",
    )
    assert len(views) == 1
    assert views[0].kind == "exposed"
    assert views[0].host_port is None


def test_stopped_container_ports_are_historical() -> None:
    views = project_ports(
        ports_payload={"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]},
        state="exited",
        network_mode="bridge",
    )
    assert views[0].kind == "historical"


def test_host_network_ports_not_collected() -> None:
    views = project_ports(
        ports_payload={"8123/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8123"}]},
        state="running",
        network_mode="host",
    )
    assert views == []


def test_ipv6_binding_family() -> None:
    views = project_ports(
        ports_payload={"443/tcp": [{"HostIp": "::", "HostPort": "443"}]},
        state="running",
        network_mode="bridge",
    )
    assert views[0].address_family == "ipv6"


def test_compose_files_absolute() -> None:
    working_dir, files = project_compose_files(
        labels={
            "com.docker.compose.project.working_dir": "/home/ohyes768/personal-web",
            "com.docker.compose.project.config_files": "/home/ohyes768/personal-web/docker-compose.nas.yml",
        }
    )
    assert working_dir == "/home/ohyes768/personal-web"
    assert files[0].path_state == "absolute"
    assert files[0].resolved.endswith("docker-compose.nas.yml")


def test_compose_files_relative_resolved_with_workdir() -> None:
    _, files = project_compose_files(
        labels={
            "com.docker.compose.project.working_dir": "/home/ohyes768/freshrss",
            "com.docker.compose.project.config_files": "docker-compose.yml",
        }
    )
    assert files[0].path_state == "relative_resolved"
    assert files[0].resolved == "/home/ohyes768/freshrss/docker-compose.yml"


def test_compose_files_relative_unknown_without_workdir() -> None:
    working_dir, files = project_compose_files(
        labels={"com.docker.compose.project.config_files": "docker-compose.yml"}
    )
    assert working_dir is None
    assert files[0].path_state == "relative_unknown"
    assert files[0].resolved is None


def test_compose_files_keeps_order() -> None:
    _, files = project_compose_files(
        labels={
            "com.docker.compose.project.working_dir": "/w",
            "com.docker.compose.project.config_files": "b.yml,a.yml",
        }
    )
    assert [item.raw for item in files] == ["b.yml", "a.yml"]


def test_projection_never_leaks_env_or_command() -> None:
    payload = container_payload()
    payload["Config"]["Env"] = ["SECRET_TOKEN=abc"]
    payload["Config"]["Cmd"] = ["--password=abc"]
    payload["Config"]["Hostname"] = "internal"
    projected = project_container(payload)
    serialized = repr(projected)
    assert "SECRET_TOKEN" not in serialized
    assert "--password" not in serialized
    assert "Env" not in projected
    assert "Cmd" not in projected
    assert "Hostname" not in projected


def test_health_not_configured_when_absent() -> None:
    payload = container_payload(health_status=None)
    projected = project_container(payload)
    assert projected["health"] == "not_configured"


def test_health_healthy_and_unhealthy() -> None:
    assert project_container(container_payload(health_status="healthy"))["health"] == "healthy"
    assert project_container(container_payload(health_status="unhealthy"))["health"] == "unhealthy"


def test_mounts_projected() -> None:
    payload = container_payload(
        mounts=[
            {
                "Type": "bind",
                "Source": "/home/ohyes768/skills",
                "Destination": "/skills",
                "RW": False,
            },
            {
                "Type": "volume",
                "Source": "/var/lib/docker/volumes/x/_data",
                "Destination": "/app/data",
                "RW": True,
            },
        ]
    )
    projected = project_container(payload)
    assert projected["mounts"][0]["kind"] == "bind"
    assert projected["mounts"][0]["read_only"] is True
    assert projected["mounts"][1]["kind"] == "volume"
    assert projected["mounts"][1]["read_only"] is False


def test_project_container_carries_image_version_label() -> None:
    """镜像 OCI 版本 label 投影进 image_version（「当前版本」第一来源）。"""
    payload = container_payload()
    payload["Config"]["Labels"]["org.opencontainers.image.version"] = "v2.5.1"
    projected = project_container(payload)
    assert projected["image_version"] == "v2.5.1"


def test_project_container_image_version_falls_back_to_revision() -> None:
    payload = container_payload()
    payload["Config"]["Labels"]["org.opencontainers.image.revision"] = "a1b2c3d"
    assert project_container(payload)["image_version"] == "a1b2c3d"


def test_project_container_image_version_absent_is_empty() -> None:
    projected = project_container(container_payload())
    assert projected["image_version"] == ""


def test_version_falls_back_to_semverish_image_tag() -> None:
    """没打 OCI label 时，版本号形态的镜像 tag 兜底（如 music-assistant:2.8.2）。"""
    projected = project_container(container_payload(image="ghcr.io/music-assistant/server:2.8.2"))
    assert projected["image_version"] == "2.8.2"


def test_non_version_tags_are_ignored() -> None:
    # nginx 在基础设施名单里，tag 兜底整体关闭；valkey:9 同理（infra 排除）
    assert project_container(container_payload(image="nginx:alpine"))["image_version"] == ""
    assert (
        project_container(container_payload(image="songloft/songloft:tmp-full-amd64"))[
            "image_version"
        ]
        == ""
    )
    assert project_container(container_payload(image="valkey:9@sha256:5463"))["image_version"] == ""


def test_v_prefixed_tag_and_label_priority() -> None:
    assert project_container(container_payload(image="x/y:v2.5.6"))["image_version"] == "v2.5.6"
    payload = container_payload(image="x/y:v2.5.6")
    payload["Config"]["Labels"]["org.opencontainers.image.version"] = "9.9.9"
    # label 优先于 tag
    assert project_container(payload)["image_version"] == "9.9.9"


def test_infra_images_do_not_provide_version() -> None:
    """基础设施镜像的版本 tag 不代表业务服务版本，不识别。"""
    assert (
        project_container(
            container_payload(image="tecnativa/docker-socket-proxy:0.2.0")
        )["image_version"]
        == ""
    )
    assert project_container(container_payload(image="postgres:14"))["image_version"] == ""
    assert project_container(container_payload(image="valkey:9"))["image_version"] == ""


def test_noninfra_label_still_wins_over_tag() -> None:
    """非基础设施镜像：label 优先于 tag 兜底（业务镜像不受排除影响）。"""
    payload = container_payload(image="myapp/app:v1.2.3")
    payload["Config"]["Labels"]["org.opencontainers.image.version"] = "9.9.9"
    assert project_container(payload)["image_version"] == "9.9.9"


def test_infra_image_label_is_excluded_too() -> None:
    """socket-proxy 镜像自带 OCI version label，同样不算业务服务版本。"""
    payload = container_payload(image="tecnativa/docker-socket-proxy:0.2.0")
    payload["Config"]["Labels"]["org.opencontainers.image.version"] = "0.2.0"
    assert project_container(payload)["image_version"] == ""
