# 执行计划:宏观信号按月过滤

前置:PRD/design 已评审。后端测试用 pytest(backend/macro 目前无 tests/ 目录,
新建)。验证命令均在 `backend/macro/` 下执行,注意 venv(CLAUDE.md 写
`./.venv/bin/uvicorn`,Windows Git Bash 下实际用 `python -m pytest`)。

## 清单

### 阶段 1:后端过滤 + 占位

- [ ] 1.1 新建 `backend/macro/tests/__init__.py`、`tests/conftest.py`
      (fixture:tmp 目录写 skill JSON,monkeypatch `get_settings` 的
      `macro_signal_data_dir`;patch `date.today` 固定「今天」让规则推算可断言)
      → 验证:`python -m pytest tests/ -v` 空 collection 不报错
- [ ] 1.2 写失败测试 `tests/test_macro_signal_month_filter.py`:
      a) 兜底路径 month=最新月:7 月 CPI 在 8 月请求中 value=null 且
         next_release_at 推算正确(CPI day=9 → 下月 9 日)
      b) 兜底路径 month=当前自然月(无任何数据落当月):全占位、不返回 null
      c) 历史空洞月(早于 latest_month 且无归档)→ None
      d) 归档月全量返回不受影响
      e) 规则表查不到的 key → 剔除不占位
      → 验证:RED(全部 fail)
- [ ] 1.3 实现 `macro_signal_service.py`:
      - `_convert_dimension_from_macro_signal` / `_convert_risk_appetite` 加
        `month: Optional[str] = None` 参数,按 design 的过滤+占位逻辑改
      - `get_snapshot` 兜底分支:计算 `latest_month`,按
        `month > latest_month` / `==` / `<` 三分支决定 全占位/过滤/null
      - `_read_latest_groups(month)` 透传 month
      → 验证:GREEN(1.2 测试全过)
- [ ] 1.4 手工冒烟:用真实数据目录跑
      `python -c "from src.services.macro_signal_service import ..."` 断言
      2026-08 快照里 CPI value=None / next_release=2026-09-09、DR007 有值;
      2026-07(归档)全量。
      → 验证:输出符合预期

### 阶段 2:前端暂未获取态 + 当前月可选

- [ ] 2.1 `GroupCard.tsx` IndicatorRow:占位分支(value=null 且有
      next_release_at)渲染「暂未获取 · 预计 ≈MM-DD 发布」,数值 '—';
      日频占位只显示「暂未获取」
      → 验证:`pnpm build` 通过
- [ ] 2.2 `MacroSignalTab.tsx`:months ∪ 当前自然月,默认选中不变逻辑
      → 验证:`pnpm build` 通过;切月份交互正常(dev server 手测)
- [ ] 2.3 手测路径:切 8 月 → 月频行「暂未获取 · 预计 ≈09-09 发布」,
      日频行正常数值;切 7 月 → 与改动前展示一致
      → 验证:浏览器目测 + 截图留档

### 阶段 3:收尾

- [ ] 3.1 `python -m pytest tests/ -v` 全绿
- [ ] 3.2 `cd apps/macro && pnpm build` 通过
- [ ] 3.3 spec 更新(若沉淀出「占位指标」契约,更新
      `.trellis/spec/` 相关文档)
- [ ] 3.4 git commit(单 commit,类型 feat)

## 回滚点

- 每阶段独立可回退;全部改动在单 commit 内,revert 即回滚。

## 风险

- `date.today()` 依赖系统时间,测试用 monkeypatch 固定,避免季节性 flake。
- 真实数据目录(F:/personal-projects/macro-fin-skill)在 CI 不存在 → conftest
  fixture 全部用 tmp_path,不触真实目录。
