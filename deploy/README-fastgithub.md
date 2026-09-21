# skill-manager 后端容器访问 GitHub（FastGithub 代理）部署说明

容器内 `git ls-remote/clone` github.com 依赖宿主机 FastGithub 代理
（直连被墙，GnuTLS -110）。FastGithub 只监听 `127.0.0.1:38457` 且为
MITM 模式（issuer=CN=FastGithub），因此需要以下三步一次性配置。

## 1. 放置 CA 证书

FastGithub 的根证书在宿主机已装进系统信任库，从那里拷出来：

```bash
ls /usr/local/share/ca-certificates/        # 找 FastGithub 的 .crt/.pem
cp /usr/local/share/ca-certificates/fastgithub*.crt \
   ~/personal-web/deploy/fastgithub-ca.pem  # 路径按实际调整
```

compose 已把它只读挂载到容器 `/etc/ssl/fastgithub-ca.pem`，并以
`GIT_SSL_CAINFO` 生效（该文件机器自生成，已加 .gitignore 不入库；
FastGithub 重新生成 CA 后需更新此文件）。

## 2. 宿主机 socat 端口转发（127.0.0.1 → docker0）

FastGithub 只听回环，容器经 `host.docker.internal`（= docker0 的
172.17.0.1）访问，需要转发：

```bash
sudo apt install -y socat
```

systemd 持久化单元 `/etc/systemd/system/fastgithub-docker-forward.service`：

```ini
[Unit]
Description=Forward docker0 to FastGithub loopback proxy
After=network-online.target docker.service

[Service]
ExecStart=/usr/bin/socat TCP-LISTEN:38457,bind=172.17.0.1,fork,reuseaddr TCP:127.0.0.1:38457
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now fastgithub-docker-forward
```

> 若 FastGithub 配置文件支持把监听地址改成 `0.0.0.0`（需确认其
> appsettings），可改配置替代本步，socat 单元停用即可。

## 3. 重建容器并验证

```bash
cd ~/personal-web
docker compose -f docker-compose.nas.yml -f docker-compose.skill-manager.nas.yml \
  up -d --build skill-manager-backend
docker exec skill-manager-backend git ls-remote https://github.com/wbh604/UZI-Skill HEAD
```

返回 SHA 即通；此后 Clone / 检查更新 / 登记均走代理。

## 排障

- `connection refused` → socat 未跑或 FastGithub 没起
- `SSL certificate problem` → CA 文件与当前 FastGithub 不匹配（FastGithub
  重装/重生后要同步更新 deploy/fastgithub-ca.pem）
- 容器 healthcheck 反复重启 → 检查 compose 里 `NO_PROXY` 是否还在
  （localhost 请求不能吃代理）
