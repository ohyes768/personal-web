# 界面人工确认住宅入口

2026-10-28：用户在短名称修复提交推送后，明确要求“界面确认住宅 开干吧”。本增补只改目录详情用途确认入口，不改后台收录规则及其他会话的新房地图实现。

## 现状与设计

- 后端已有 /directory/workflow/catalog/{cid}/use-review/confirm，保存人工结论、校验revision及人工排除/锁，确认后仍按区域/地址等条件计算收录。
- 详情只在use_review对象存在时渲染用途面板，按钮埋在定位面板后；position_type_missing未自动打开表单，入口不明显。不能断言缺入口本身造成了后端收录问题。
- 对真实主档且未被人工排除/锁保护的未收录小区开放确认。位置已确认但类型缺失时，在基本信息提示旁提供“确认住宅用途”快捷入口，打开并定位到现有表单；不要求先重新查询高德。
- 缺少use_review投影也可进入现有确认流程；来源未关联、已删除/合并、无审核revision、人工排除/锁继续禁用。正常已收录且无复核需求不增加日常操作。
- 沿用原有住宅/别墅/排屋、非住宅与理由控件，增加说明：人工结论只确认用途，区域/地址等收录条件仍须满足。确认后复用原有刷新详情、列表、地图通知。

## 验收

1. position_type_missing + 已定位主档可见快捷入口，打开住宅确认表单，不依赖已有用途结果。
2. 来源未关联、已删除/合并、审核锁或人工排除没有可提交入口；busy和缺revision时不能提交。
3. 提交沿用版本化接口与完整刷新逻辑，不增加静默自动确认。
4. 组件测试先失败后实现；前端测试、lint和tsc验证，不提交或部署其他会话的新房地图文件。

## 实现与验证

- 改动仅DirectoryFlowWorkspace.tsx、UseReviewPanel.tsx及use-review.test.cjs；catalogCanConfirmUse集中判定可确认的主档，CatalogUseReviewSection允许缺失use_review时显示既有表单。position_type_missing基本信息区提供快捷入口并滚动到表单，默认展开。提交沿用既有revision接口及刷新逻辑。
- 新增3项回归先失败后通过：缺类型且无用途投影可确认、身份/人工锁保护、缺revision不可提交。组件测试18项通过。
- 共享工作区前端测试150项通过；其整体tsc在另一会话未完成的新房页面报错，未改这些文件。完整lint当时0错误、5个其他会话页面的未使用导入警告。
- 采用HEAD ffdc484的前端源码加本次3个文件建立隔离副本：140项前端测试、lint、tsc全部通过。首次C盘副本构建遇到依赖junction跨盘Webpack路径解析问题；改用F盘隔离副本后next build --webpack成功（编译、类型检查、静态生成、standalone打包均成功）。
- 隔离页面http://localhost:3018/map，Playwright拦截全部/api/map请求并提供模拟钱江彩虹城position_type_missing主档，没有访问或改写生产数据。验证快捷入口可见、默认确认住宅、表单可提交；模拟接口校验revision=1、decision=residential、property_type=住宅；提交后人工结论与成功提示显示，已收录(1)/待处理(0)刷新。390px窄屏无横向溢出；已检查桌面与窄屏截图。
- 截图位于本会话visualizations目录residential-confirm-desktop.png及residential-confirm-mobile.png，临时副本和脚本位于.gitignore内的.tmp/use-confirmation-check，不入库。
- 本次未提交Git、未部署NAS前端；其他会话的新房地图文件保持原样。
