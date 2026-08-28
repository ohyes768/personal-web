# fund-flow 改用 curl_cffi 绕过东财 TLS 指纹反爬

## Goal

修复持续失败的大盘资金流数据源:`POST /api/update/fund-flow` 及其定时任务
(a_share_daily 组内)自 2026-08-27 起全部 failed。

## 根因(2026-08-28 排查确认)

`ak.stock_market_fund_flow`(module `akshare.stock.stock_fund_em`)请求东财
`push2his.eastmoney.com/api/qt/stock/fflow/daykline/get`:

- 服务端按 **TLS 客户端指纹**拦截:Python requests/urllib3 与 httpx(OpenSSL 栈)
  → 连接直接 RST(RemoteDisconnected);curl(Schannel)→ 放行返回完整数据
- 非代理/非接口下线/非限流问题;本地与生产(OpenSSL 栈)行为一致
- akshare 全系基于 requests,等上游修复不可行

## 方案

`backend/macro/src/services/fund_flow_service.py` 的 `fetch_all_fund_flow` 不再调
`ak.stock_market_fund_flow`,改为 **curl_cffi**(`impersonate="chrome"`)直连同一东财
接口:

- URL/params/headers 复刻 akshare 1.18.38 现实现(含 ut token、secid/secid2 双市场)
- 解析逻辑复刻:klines split → DataFrame,**列名与现有输出完全一致**
  (中文列名),保证 `calculate_cumulative_flow` / routes 下游零改动
- 失败语义保持:异常路径与现有 tenacity retry 兼容
- `pyproject.toml` 增加 `curl_cffi>=0.7`

## Acceptance Criteria

- [ ] 本地直连真实东财接口成功拉到数据(≥60 行,最新日期为最近交易日)
- [ ] `POST /api/update/fund-flow`(本地起服务)返回 success
- [ ] 新增单测:mock curl_cffi 响应 → 解析列名/行数/数值正确;网络异常 → 异常路径正常
- [ ] 既有 fund-flow 相关测试全绿;全量 pytest 不回归
- [ ] 其它数据源与 scheduler 逻辑零改动

## 最终结论(2026-08-28 深入排查后)

curl_cffi 假设**被证伪**,任务以"客户端侧无法修复"关闭:

1. `push2his.../fflow/daykline/get` 对**真实 Chrome 浏览器**也返回
   `ERR_EMPTY_RESPONSE`(devtools 实测)——非指纹反爬,东财侧关闭/改版中该接口
2. curl_cffi impersonate chrome/edge/safari/firefox 全部被 RST;HTTP 明文、
   三个 CDN 节点(103.220.167.80 / 140.207.67.156 / 101.226.30.221)全部被拒
3. `push2.../fflow/kline/get`(浏览器可通)klt=101 仅返回当天 1 条 5 列,
   无历史序列;且 python requests/curl_cffi 同样被拦,不可用
4. akshare 升级至 1.18.94(已提交依赖更新,77 测试全绿):URL 未变,同样失败,
   上游未修
5. `datacenter-web.eastmoney.com` 对 python 放行,但无大盘资金流报表

处置:fund-flow 数据源维持 failed(不影响组内其它 5 源);后续 akshare 升级或
东财恢复后重试即可。参考:akshare issue #7005(服务器部署被检测断开,普遍问题)。
