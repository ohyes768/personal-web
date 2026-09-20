# Windows 开发机 Python 测试环境契约

> 来源：09-20-skill-publish-console 任务（backend/skill-manager）。适用所有在 Windows 上开发、测试跑 pytest 的 Python 后端（uv 项目）。

## 1. Scope / Trigger

- 在 Windows 开发机上为本仓库 `backend/<name>` 写或跑 pytest 测试
- 测试涉及 symlink、原子替换（`os.replace`）、`tmp_path`、或需要 Windows/WSL 双侧验证

三条硬约束都源于本机真实踩坑，违反的症状见 §4 错误矩阵。

## 2. 契约

### 2.1 pytest basetemp 必须重定向到项目所在盘

```toml
# backend/<name>/pyproject.toml
[tool.pytest.ini_options]
addopts = "--basetemp=.pytest-tmp"
```

**Why**：本机 `%TEMP%`（C: 盘用户目录）上 `os.replace`/`os.rename` 报 `WinError 6 句柄无效`；项目盘（F:）正常。默认 tmp_path 在 %TEMP%，凡测试原子文件操作的用例会随机失败。`.pytest-tmp/` 必须随项目加入 `.gitignore`。

### 2.2 symlink 测试必须打 `requires_symlink` marker

未提权且未开开发者模式的 Windows 上 `Path.symlink_to` 报 `WinError 1314`（需特权）。conftest 探测特权后对无特权环境 skip，禁止伪造文件语义（用普通目录冒充 symlink 会让断言失去意义）：

```python
# tests/conftest.py — 探测一次，全局标记
def _can_symlink(tmp_path: Path) -> bool:
    probe = tmp_path / "probe"
    try:
        probe.symlink_to(tmp_path)
        probe.unlink()
        return True
    except OSError:
        return False

REQUIRES_SYMLINK = pytest.mark.skipif(
    not _can_symlink(...), reason="需 symlink 特权（开发者模式或管理员）",
)
```

```python
# 用法：凡断言真实 symlink 落点/解析目标的测试
@pytest.mark.requires_symlink
def test_publish_creates_symlink(...): ...
```

**WSL 等效验证**：`requires_symlink` 跳过的测试可在 WSL Ubuntu 中对同一 checkout 全量跑通（真实 Linux symlink 语义），作为提权前的替代验证。Windows/WSL 两侧结果都要写进任务验证记录。

### 2.3 Windows 与 WSL 不得共用 `.pytest-tmp`

并行跑两侧 pytest 会互删对方的 tmp_path 编号目录（`FileExistsError`、git clone 对象缺失等伪失败）。并行时给两侧不同 basetemp（如 WSL 侧 `-o addopts="--basetemp=.pytest-tmp-wsl"`），或严格串行。

## 3. Wrong vs Correct

```text
# Wrong：在 %TEMP% 上测原子替换 + 无 marker 直跑 symlink 断言
tmp_path / "dst" 上 os.replace(...)   → WinError 6
test_publish(): assert link.is_symlink()  → WinError 1314（无特权机器）

# Correct：basetemp 重定向 + requires_symlink marker（+ WSL 复验）
pyproject addopts = "--basetemp=.pytest-tmp"
@pytest.mark.requires_symlink def test_publish(): ...
```

## 4. Validation & Error Matrix

| 症状 | 根因 | 处置 |
|------|------|------|
| `os.replace` 报 WinError 6，仅部分目录复现 | tmp_path 落在 %TEMP% | basetemp 重定向项目盘 |
| `symlink_to` 报 WinError 1314 | 无 symlink 特权 | marker skip + WSL 复验 |
| pytest 全量出现 FileExistsError / clone 对象缺失等伪失败 | Windows/WSL 共用 .pytest-tmp | 分侧 basetemp 或串行 |
| git 清理报只读文件删不掉 | git 对象带只读位 | rmtree onexc 清 `S_IWRITE` 后重试 |

## 5. 相关

- 实例：`backend/skill-manager/tests/conftest.py`、`backend/skill-manager/pyproject.toml`
- 已知环境噪音：本机 sys.path 存在跨项目污染（pytest 曾把 `src.models` 解析到其他项目）；`src/__init__.py` 存在时本项目包优先，仍建议测试命令都在项目目录内执行
