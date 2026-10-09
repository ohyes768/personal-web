# Design：首页门户升级 — 静态驾驶舱

## 1. 文件布局与挂载

```
nginx/
├── web.conf          # 改 location = / + 补 4 条 health 转发
└── html/
    └── index.html    # 单文件首页（内联 CSS/JS，无构建）
```

NAS nginx 容器（独立 compose，`~/-/nginx/`）**一次性**加目录 bind mount：

```yaml
volumes:
  - <仓库路径>/nginx/html:/var/www/personal:ro
```

- 挂**目录**不挂单文件：单文件 bind mount 在文件替换（git pull 重写 inode）时不跟随，正是 web.conf 曾踩过的坑（deploy 脚本注释 150-154 行）
- 之后改 `index.html`：git pull 即生效（nginx 每请求重新 open 静态文件，无需 restart）；只有改 `web.conf` 才需要 `./scripts/deploy-nas.sh nginx`

## 2. web.conf 改动

### 2.1 根路径（替换现有 return 200 内联 HTML）

```nginx
# 首页：静态驾驶舱（nginx/html/index.html，bind mount 到 /var/www/personal）
location = / {
    root /var/www/personal;
}
```

`root` + 默认 `index index.html`：请求 `/` → `/var/www/personal/index.html`。精确匹配 `=` 不影响其他 location。

### 2.2 health 转发补齐（4 条精确匹配，插在对应前缀 location 之前）

```nginx
# fund-select health：主 router prefix 是 /api/funds，不能走 /api/funds/ 的剥前缀 rewrite
location = /api/funds/health { proxy_pass http://fund_select_backend; proxy_set_header Host $host; }
# skill-manager health：后端实际路径是 /api/health（非 /api/skills/health）
location = /api/skills/health { rewrite ^ /api/health break; proxy_pass http://skill_manager_backend; proxy_set_header Host $host; }
# douyin / kids：health 在根路径 /health，无 /api 前缀
location = /api/douyin/health { rewrite ^ /health break; proxy_pass http://douyin_backend; proxy_set_header Host $host; }
location = /api/kids/health   { rewrite ^ /health break; proxy_pass http://kids_catalog_backend; proxy_set_header Host $host; }
```

nginx 精确匹配优先于前缀匹配，位置无讲究，但按服务分组放、带注释说明"为什么不走已有前缀规则"。

统一对外口径：**前端一律 fetch `/api/<svc>/health`**，真实路径差异由 nginx 抹平。

## 3. index.html 设计

### 3.1 结构：数据驱动的卡片网格

```html
<script>
const APPS = [
  { key: 'dividend', name: '股息率分析', href: '/dividend/', icon: '📈',
    health: '/api/dividend/health',
    kpi: async () => {...} },   // 返回 {label: 'Top 股息率', value: '6.2% 中远海控'}
  ...
];
</script>
```

- 页面骨架纯静态（无 JS 也能看到卡片和链接，只是没有状态点/KPI —— 渐进增强）
- JS 启动后并行 fetch 各卡片 health + KPI，逐卡填充

### 3.2 视觉规范（对齐既有 UI 偏好）

- 暖白纸底 `#faf9f6`，卡片白色 `#fff` + 细边框 `#e8e5df`，圆角 10px
- 系统字体栈；移动端单列、桌面 2-3 列网格
- 状态点：8px 圆点（绿 `#3a9a50` / 红 `#c0453e` / 灰=检测中），点旁小字 "在线/离线"
- 数据密控件疏：卡片主体是 KPI 数字（大号）+ 名称，无多余按钮；整卡可点击

### 3.3 KPI 数据源（第一版，字段已对照后端模型/规范确认）

| 卡片 | 接口 | 取值 | 已确认的响应形状 |
|------|------|------|------|
| dividend | `GET /api/dividend/stocks?min_yield=5` | `items[0].name` + `avg_yield_3y`（默认即按 3 年平均股息率降序） | `{total, items: [DividendStock], last_updated}`；`avg_yield_3y` 是默认排序字段；接口无分页参数 |
| macro | `GET /api/macro/daily-snapshot` | `usd_cny`（美元/人民币，主）+ `cn_us_10y_spread`（中美利差，副） | `data.groups.exchange_rate.indicators[]` 按 `key` 找；契约见 spec `macro-daily-snapshot.md`。注意：daily-snapshot **没有**美债 10Y 独立 key |
| housing-map | `GET /api/map/market-reference` | `data.overall.avg_price` + `mom_percent` | `{success, data: {overall: {avg_price, mom_percent, yoy_percent}, source: {captured_at}}}`（快照时间在 `data.source` 下） |
| rss / douyin / funds / skills / kids | — | 仅状态点 | KPI 后续任务补 |

### 3.4 fetch 策略（降级即 UI 诚实）

- `AbortSignal.timeout(5000)` 并行请求；失败/超时 → 该卡状态点红 + KPI 区显示 "—"
- 任何单卡失败不影响其他卡（每卡独立 try/catch），页面永不白屏
- 无环境判断：本地 file:// / http.server 预览时全部显示离线，符合预期

## 4. 兼容与回滚

- 不动 `/_next/static`、不动任何 app 的 location → 对 8 个应用零影响
- 回滚：`git revert` web.conf（+ restart nginx）；`nginx/html/` 留着无害
- 部署顺序：先加 NAS 挂载并 restart nginx（此时 conf 还是旧的，无影响）→ 再部署新 web.conf

## 5. 权衡记录

- **不建 Next.js 门户应用**：basePath='' 与 dividend 冲突（连锁改 dividend basePath + location 规则），且 root 可用性从"永远在线"退化为依赖容器；静态文件方案零此风险
- **不补后端 summary 聚合接口**：第一版三个 KPI 均可从现有单接口取；若 dividend /stocks 响应实测过重（>200ms 或过大），第一版降级为仅状态点，KPI 做成后续任务
