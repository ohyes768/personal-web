# 验证与交付记录

日期：2026-10-13（Asia/Shanghai）。实现和本地验证完成，功能提交 ab9ab74；未部署。用户已授权提交并推送，本次收尾归档任务。

## 已实现
- 小区数据管理独立主 Tab，统一小区/来源名称视图、分页、名称搜索、区域/来源/状态过滤；默认滨江。
- SQLite 统一目录；整理现有 TMSF、Fang 人工映射/拒绝记录、来拍记录，原文件备份，保留旧 ID。重启不覆盖人工维护。
- 四来源名称采集适配器、进度/取消/报告；区域列表发现独立于租金映射。自动关联需唯一完整名/别名、区域及地址或位置证据；冲突待确认。
- 标准名/别名编辑、手动关联/拒绝/解除、新建并关联（单事务）、合并，整小区删除及所有已关联来源跳过，恢复与操作留痕。
- 地图、价格/租金/法拍查询与详情刷新消费有效目录决策。未关联租房样本保存后可在关联完成时重算，区域样本明确标注。
- 已删除同名但新 ID 的来源提示，避免全局名称黑名单。来拍保留资产观察的拍卖轮次 ID，已知删除轮次不再请求详情。

## 检查证据
- 后端全套 pytest：291 passed，2 条现有 FastAPI/Starlette 弃用警告；Windows basetemp 在项目盘，命令 `.venv/Scripts/python.exe -m pytest tests -q --basetemp=.pytest-tmp-directory-quality`。
- 前端完整 node 测试：36 passed；新增测试覆盖来源身份/方法/依据及安全链接。
- TypeScript `node node_modules/typescript/bin/tsc --noEmit` 与 ESLint `node node_modules/eslint/bin/eslint.js` 通过。
- 生产构建 `node node_modules/next/dist/bin/next build --webpack` 成功，静态路由生成完成。
- 浏览器隔离数据：现有670条目录复制到 `.tmp/housing-directory-preview`；验证来源“验证花园”创建并关联 → 整小区删除 → 恢复 → 统一目录检索。全部动作真实调用本地 API，未修改服务原始 data。
- 桌面及390px手机截图已查看，无管理页横向溢出，表单/确认操作正常；截图 `.tmp/housing-directory-desktop.png`、`.tmp/housing-directory-mobile.png`。
- `git diff --check` 通过。其他 skill-manager 和 nginx 改动属于并行工作，未覆盖。

## 覆盖与实际限制
- 不承诺完整区域覆盖；Fang/来拍分页截断与来源失败保留报告；Amap 每个搜索最多200条/8页，按官方文档限制报告截断。
- Amap 必须有 Web 服务 Key，支持环境变量或现有 `_gaode_config.py`；本轮没有运行四来源全区抓取，避免把接口接入与全量采集混为一谈。来源实时完整性需运行采集后以报告核对。
- 自动位置证据阈值为100m，且必须有完整名称及唯一候选；相似名或缺位置/地址不自动确认。
- 当前租金快照模型每小区只允许一个 Fang 小区来源，关联冲突返回409并要求先解除错误来源。
- 不包含小区边界手绘编辑。已有边界状态可查看，缺边界不阻碍名称维护。
- 本地预览后台使用隔离数据；服务真正上线首次运行会整理当前 data 并备份，此后只维护 community_registry.sqlite3。
