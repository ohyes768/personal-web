# 执行计划

## 步骤

1. **共享层**：新建 `lib/ui.ts`；泛化 `ConfirmActionDialog`（danger/confirmLabel 已有/requirePassword/completedLabel）
   - 验证：`pnpm lint` + 既有测试（ConfirmActionDialog 无独立测试文件，靠两个 Manager 的测试覆盖）
2. **ExportTargetManager**：共享常量替换局部常量；删除弹窗改 ConfirmActionDialog（requirePassword=false + danger + blocked 完成态 + onManage 跳转）；error 块加重试；onNotify
   - 验证：`pnpm test` 中相关用例 + 浏览器实测（删除弹窗被拦/未拦两态）
3. **InstallTargetManager**：prettier 化 + 对齐基准（页头/单列/卡三层/徽章/空态/loading/错误块/表单弹窗 shadow+focus/删除 danger 确认/onNotify）
   - 验证：`pnpm test` 相关用例 + 浏览器实测两 tab 对照
4. **page.tsx 接线**：onNotify / onManage
   - 验证：写操作后 notice 出现
5. **全量检查**：`pnpm lint && pnpm test && pnpm build`；浏览器批量走查（两 tab + 四种弹窗 + notice + 空态）；`impeccable detect` 跑一次改动文件

## 验证命令

```bash
cd apps/skill-manager
pnpm lint
pnpm test
pnpm build
```

## 浏览器走查清单（localhost:3008/skills，本地前后端已在跑）

- [ ] 安装目标 tab：页头（标题+说明+刷新+新增）/ 单列卡 / 徽章 / 空态（本地 dev 数据有目标，空态用 React 验证或临时移除数据跳过）/ 错误块样式
- [ ] 导出目标 tab：与安装 tab 同构对照
- [ ] 弹窗四态：安装·保存（sky+密码）、安装·删除（rose+密码+blocked 完成态「知道了」+进入看板）、导出·删除未拦（rose 无密码）、导出·删除被拦（完成态+跳管理看板）
- [ ] notice：新增/删除/启停成功后出现
- [ ] focus 样式：所有输入框 focus:border-sky-500

## 回滚点

单仓库提交，任一步失败 `git checkout -- <file>` 即回滚；无数据迁移。

## 完成定义

prd.md 验收标准全勾 + 截图留证（.trellis/workspace/jackson.tang/screenshots/）+ commit。
