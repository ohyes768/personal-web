# 已有研究和规范核对

## 研究来源

来自同一聊天在study中的离线研究，图与参数已实际生成并核对；不是生产服务的实时状态。
原始说明：`F:/personal-projects/study/docs/index-trends/csi300-chart-implementation.md`。
旧service-design.md以固定步进窗口为当前模型，已经被本任务“两Tab+当前两模型选择”的需求覆盖，不能不加修订直接迁移。

研究基准：2005-04至2026-09，共258个完整月；120月窗口/36月步进产生4组。四组只看回归为4图，三算法对照才是12图。
主月K来源腾讯sh000300；新浪日线与月最高/最低/收盘核对，精度约0.005点，研究脚本容差0.011点。

公式：月序号x从0起；OLS中线a+b*x；deviation=sqrt(mean((close-(a+b*(x+1)))²))；上/下轨=中线±2*deviation。
保留移植公式前移一根K线细节，版本`lrc-ltb-port-v1`；不宣称95%预测区间。
算法参考：
- https://www.tradingview.com/script/efXI515C-Linear-Regression-Channel/
- https://www.tradingview.com/script/go0gMpJm-Linear-Regression-Channel-Screener-Daveatt/
- https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000300,month,,,1000,qfq

## 任务目录的固定资料

- `research/fixtures/csi300-monthly-2026-09.json`：258个月的标准OHLC及来源，作为脱网数值验证输入。
- `research/fixtures/csi300-baseline.json`：四组固定窗口，以及同截止月近10年/全历史模型的基准系数。
- `research/reference-linear-window4.png`：已有第4组回归图，只作为图形语义参考，不强制复刻研究图的全部视觉风格。

首月是正式发布后的部分月，不混入2002年起的回溯日线。当前近10年截至2026-09时为2016-10至2026-09，与固定窗口第4组不同。

## 仓库规范和可复用位置

- `.trellis/spec/guides/new-service-onboarding.md`：新服务接入9个点；纯前端、无BFF默认；内部`/api`与外部业务前缀映射；端口需重新核实。
- `.trellis/spec/frontend/index.md`、`macro-echarts.md`：图表日期、隐藏Tab与resize、tooltip、375px/1440px验证。macro当前是ECharts，旧Plotly规范不是当前默认。
- `.trellis/spec/backend/dividend-select/backend/code-type-guidelines.md`：股票与指数代码全链路字符串。
- `.trellis/spec/backend/dividend-select/backend/scheduler-lifecycle.md`：APScheduler 3.x关闭取消语义、显式drain和有界等待。
- `.trellis/spec/backend/global-macro-fin/backend/scheduler.md`：Asia/Shanghai、单worker、HTTP self-call复用刷新锁、weekday使用英文名称。
- `.trellis/spec/backend/testing-environment.md`：Windows测试临时目录与隔离规范。
- `backend/dividend-select/src/services/dingtalk_notifier.py`：已有Markdown通知实现，仅参考机制，不读取/复制/启用实际Webhook。
- `nginx/web.conf`、`docker-compose.nas.yml`、`scripts/deploy-nas.sh`：部署接入必须同时检查。

## 已知限制

旧README端口和服务数量不是实时清单；现有default_package是无关的douyin后端，新任务不应归入它。代码模式取证并不等于所有模块可跨服务直接导入。
模型长度10年、宽度2只是已研究口径，不是被证明最优的交易策略。回溯样本重叠7年；覆盖率高可能来自通道宽。
