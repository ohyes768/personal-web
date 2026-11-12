# NAS 的 HTTPS 证书（Let's Encrypt 通配符）

> 2026-11-12 之前 NAS 用的是自签证书（`CN=duomi77` 自签自己），浏览器每次弹警告，
> `curl` / 脚本 / 手机 App 直接拒绝。本文记录换成 Let's Encrypt 后的做法与坑。

## 1. 现在是什么状态

| 项 | 值 |
|---|---|
| 证书 | `*.duomi77.cn` + `duomi77.cn`（Let's Encrypt，EC P-256） |
| 位置 | `~/nginx/ssl/le.crt`、`le.key`（nginx 容器挂成 `/etc/nginx/ssl/`） |
| 有效期 | 90 天，cron 每 6 小时检查一次，到期前 30 天自动续 |
| 验证方式 | DNS-01（阿里云 `dns_ali`），**不需要对外开 80 端口** |
| 续期后 | 自动 `docker exec nginx nginx -s reload` |

一条命令看状态：

```bash
./scripts/setup-ssl-cert.sh status
```

输出包含：证书主体/签发者/有效期、剩余天数、下次续期时间、**线上实际提供的证书序列号**
（用来确认 reload 真的生效了）、cron 任务。

## 2. 为什么用 DNS-01 而不是 HTTP-01

1. **通配符证书只能用 DNS 验证**——Let's Encrypt 对 `*.example.com` 只接受 DNS-01。
2. 不用把 80 端口暴露到公网。NAS 在内网，路由器就算没做 80 端口映射也能签。

代价是每次续期要向 DNS 加一条临时 TXT 记录，所以需要一个有 DNS 权限的 AccessKey。

## 3. AccessKey 从哪来

两种都行：

**A. 复用 ddns-go 里那把（推荐，省事）**

ddns-go 本来就在用 alidns 更新解析，权限正好够。脚本默认直接从容器读：

```bash
./scripts/setup-ssl-cert.sh issue
```

**B. 自己在阿里云 RAM 建一把独立的**

只授 `AliyunDNSFullAccess`（别给 AdministratorAccess）。建好后：

```bash
export Ali_Key="LTAI..."
export Ali_Secret="..."
./scripts/setup-ssl-cert.sh issue
```

密钥会自动存进 `~/.acme.sh/account.conf`（权限 600），**cron 续期时不需要你再 export**。

> 不要用 sslforfree / freessl 这类网站。它们面向"只有 CSR、没法碰服务器"的人，
> 手动上传下载、90 天一次，正好是最不能自动续期的方式。

## 4. 首次签发做了什么

```bash
./scripts/setup-ssl-cert.sh install   # 装 acme.sh，默认 CA 切到 Let's Encrypt
./scripts/setup-ssl-cert.sh issue     # 签发 + 安装 + 挂 reload 钩子
```

`install` 里有一处是必须的：acme.sh 3.x 默认 CA 是 **ZeroSSL**，要显式切回
Let's Encrypt，否则会多一层账号注册（要邮箱 + EAB）。

## 5. 把 nginx 指到新证书

签发只是把文件放到 `~/nginx/ssl/le.crt`，nginx 各 conf 还要改引用：

```bash
cd ~/nginx
for f in *.conf rss/*.conf; do
  sed -i 's|ssl_certificate */etc/nginx/ssl/server\.crt;|ssl_certificate /etc/nginx/ssl/le.crt;|' "$f"
  sed -i 's|ssl_certificate_key /etc/nginx/ssl/server\.key;|ssl_certificate_key /etc/nginx/ssl/le.key;|' "$f"
done
```

涉及 10 个文件：`web.conf` `dsh.conf` `rss/rss.conf` `xiaomusic.conf` `songloft.conf`
`immich.conf` `homeassistant.conf` `file-system.conf` `openclaw.conf` `stock.conf`。

### ⚠️ 两个真实的坑

**坑 1：`sed -i` 会把软链换成普通文件。**

`~/nginx/web.conf` 是指向仓库 `personal-web/nginx/web.conf` 的软链。
`sed -i` 的语义是"写新文件再改名"，结果软链被替换成一个独立副本，
之后改仓库文件对容器就不生效了。改完要检查：

```bash
ls -la ~/nginx/web.conf     # 必须是 lrwxrwxrwx ... -> /home/ohyes768/personal-web/nginx/web.conf
```

被替换了就这样恢复（先把改动同步进仓库那份）：

```bash
rm -f ~/nginx/web.conf && ln -s ~/personal-web/nginx/web.conf ~/nginx/web.conf
```

**坑 2：改完 conf 只 `reload` 不够，必须重建容器。**

nginx 的 conf 是**单文件 bind mount**（`~/nginx/web.conf → /etc/nginx/conf.d/web.conf`）。
单文件挂载绑定的是 inode，`sed -i` 换了 inode，容器里看到的还是旧内容——
`nginx -s reload` 读的还是旧文件，怎么 reload 都变不过来。

```bash
cd ~/nginx && docker compose up -d --force-recreate nginx
```

证书文件本身是**目录挂载**（`~/nginx/ssl → /etc/nginx/ssl`），
所以续期时 acme.sh 写新文件 + reload 就能生效，不用重建。

## 6. 验证

```bash
# 1) 证书链能否通过系统信任库
openssl s_client -connect 127.0.0.1:9443 -servername web.duomi77.cn </dev/null 2>/dev/null \
  | grep "Verify return code"
# 期望：Verify return code: 0 (ok)

# 2) 所有 ssl 端口逐一验证
for p in 443 1443 2443 3443 6443 7443 8443 9443 10443 12443; do
  echo -n ":$p -> "
  timeout 8 openssl s_client -connect 127.0.0.1:$p -servername web.duomi77.cn </dev/null 2>/dev/null \
    | grep -o "Verify return code: .*"
done

# 3) 真的用浏览器规则访问（不加 -k）
curl -s -o /dev/null -w "%{http_code}\n" https://web.duomi77.cn:9443/services
```

2026-11-12 实测：10 个端口全部 `0 (ok)`，`curl` 不加 `-k` 也是 200。

> `:5443` 无响应是**原有问题**，跟证书无关：nginx 容器根本没发布 5443 端口，
> 那条 homeassistant 反代从外部一直就连不上。

## 7. 续期怎么保证不出事

- cron 每 6 小时跑一次 `acme.sh --cron`，到期前 30 天才会真的续。
- 续期成功后自动执行 `--reloadcmd`（`docker exec nginx nginx -s reload`）。
- reload 命令用的是 `docker` 绝对路径 `/usr/bin/docker`，在 cron 的默认 PATH 里，
  不依赖交互式 shell 的环境。

**演练过一次**（`--renew --force`），整条链路通：签发 → 安装 → reload → 序列号立即变化。
想再演练：

```bash
./scripts/setup-ssl-cert.sh renew    # 注意：这会真的重新签一张（LE 有速率限制，别频繁跑）
```

Let's Encrypt 的速率限制：同一域名 **每周 5 张**重复证书。正常续期 60 天一次，碰不到。

## 8. 回滚到自签

```bash
cd ~/nginx
for f in *.conf rss/*.conf; do
  sed -i 's|ssl_certificate */etc/nginx/ssl/le\.crt;|ssl_certificate /etc/nginx/ssl/server.crt;|' "$f"
  sed -i 's|ssl_certificate_key /etc/nginx/ssl/le\.key;|ssl_certificate_key /etc/nginx/ssl/server.key;|' "$f"
done
cd ~/nginx && docker compose up -d --force-recreate nginx
```

旧的 `server.crt` / `server.key` 没删，还在 `~/nginx/ssl/`。

## 9. 证书到期了但没续上怎么办

按顺序查：

1. `crontab -l | grep acme` —— cron 任务还在吗
2. `./scripts/setup-ssl-cert.sh status` —— 下次续期时间、线上证书序列号
3. `~/.acme.sh/acme.sh --cron --home ~/.acme.sh --debug` —— 手动跑一次看报错
4. `~/.acme.sh/account.conf` 里 `SAVED_Ali_Key` / `SAVED_Ali_Secret` 还在吗
   （AccessKey 被禁用或删除时续期会失败，这是最常见的原因）

service-manager 的管理台会在到期前 **30 天**把证书标成「即将到期」（橙），
所以不用靠记忆——打开 `/services` 的「资源总览 → 证书」就能看到还剩几天。
