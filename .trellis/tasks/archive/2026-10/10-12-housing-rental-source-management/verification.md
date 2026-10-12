# 验收记录（2026-10-12）

## 自动检查
- 后端全量：`.venv/bin/python -m pytest -q --basetemp /private/tmp/personal-web-rental-final`，278 passed。两个依赖弃用提示为环境原有提醒。
- 前端：`npm run build`（包含 TypeScript 检查）、`npm run lint`、`node --test tests/*.test.cjs`，33 passed。
- `git diff --check`、Python compileall 通过。
- 旧映射一次性迁移、旧数据卷 seed、确认候选/唯一性/拒绝及恢复、刷新与修改互斥、改绑旧快照隔离均有测试。

## 真实来源与浏览器
- 使用项目 FangClient 低频读取公开租房页。`/house/?keyword=璞悦湾` 及测试的旧式关键词路径返回全市房源；搜索表单公开接口 404，候选提示接口跳转首页。未绕过登录或挑战。程序校验 pageConfig.keyword，忽略关键词时返回可解释502，避免随机候选。
- 璞悦湾 `https://zu.fang.com/hz/house-xm2011095896/` 成功读取 structured community link，并从一条详情得到“杭州滨江区滨文路与西浦路交叉口”。
- 生产构建 + 本地 nginx 等效临时代理验收；关联数据库/租金目录放在 `/private/tmp/personal-web-rental-preview-data`，不修改实际关联与租金快照。
- 顶部“租金来源”可打开管理；已有三条关联自动迁入；搜索小区、读取真实URL候选、核对证据、二次确认保存均通过。
- 390×844 手机尺寸：弹窗居中，关闭头部滚动可见；实际DOM viewport=384、scrollWidth=384，无新增横向溢出。桌面与数据看板顶部均可见更新和管理入口。
- 临时数据库清空关联后，顶部更新返回提示与“查找租金来源”按钮，点击进入管理弹窗；未发起全量租金抓取。
- 本地无地图密钥时显示降级信息，租金管理/看板继续可用。

## 当前边界
- 自动关键词发现当前不可稳定使用，已提供并验证来源链接导入，不自动确认候选。
- 未部署、未修改NAS数据卷、未执行全量线上采集。
- 代码待用户按项目 workflow 确认提交；归档和会话记录在提交后执行。

## 收尾
用户已确认提交方案。功能提交 `e6c6c7e`，任务按流程归档并记录会话；未推送、未部署。
