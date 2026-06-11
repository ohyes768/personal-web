# Host 网络模式部署说明

> **已废弃** — 本文档描述旧架构的 host 网络部署方式，仅供参考。
>
> 当前架构使用独立应用模式，请参考 [deployment.md](deployment.md) 进行 NAS 部署。

## 旧架构说明

旧架构中，Gateway 使用 `network_mode: host` 直接访问宿主机上运行的 douying-collect 服务。

### 优点
- 直接访问宿主机服务，无需配置复杂的网络
- 性能更好，减少 NAT 转换
- 配置简单：`DOUYIN_SERVICE_URL=http://localhost:8093`

### 缺点
- 端口冲突风险 — Gateway 占用宿主机端口 8080
- 安全性略低 — 容器直接连接到宿主机网络

### 网络架构（旧）

```
服务器(宿主机)
├── douying-collect (独立运行，监听 localhost:8093)
├── api-gateway (host 网络模式)
│   ├── 直接访问宿主机网络
│   └── 访问 douying-collect: http://localhost:8093
└── personal-web-frontend (bridge 网络模式)
    └── 端口映射: 3000:3000
```

## 当前架构（推荐）

当前使用 Docker Compose + 外部 Nginx 的标准部署方式：

```
外部 Nginx (:80)
├── /dividend/*     → dividend-frontend:3003
├── /api/dividend/* → dividend-backend:8092
├── /douyin/*       → douyin-frontend:3004
└── /api/douyin/*   → douyin-backend:8093
```

具体请参考 [deployment.md](deployment.md)。

## 相关文档

- [DOCKER_DEPLOY.md](../DOCKER_DEPLOY.md) — Docker 快速部署
- [deployment.md](deployment.md) — 详细部署文档
- [服务器部署指南.md](服务器部署指南.md) — 服务器部署步骤
