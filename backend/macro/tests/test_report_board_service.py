"""报告看板 service 单元测试

隔离策略:
- macro_report_data_dir 指向 tmp_path(经 pyproject basetemp 重定向到项目盘,
  见 .trellis/spec/backend/testing-environment.md:原子写测试不得落 %TEMP%)
"""
import pytest

from src.services import report_board_service as rbs
from src.services.report_board_service import ReportBoardService

SOURCE_A = "a-share-macro-impact-skill"
SOURCE_B = "bond-market-macro-impact-skill"


class _FakeSettings:
    """最小 Settings 替身:report_board_service 只用到 macro_report_data_dir"""

    def __init__(self, data_dir: str):
        self.macro_report_data_dir = data_dir


@pytest.fixture
def service(tmp_path, monkeypatch):
    """数据目录指向 tmp_path 的全新 ReportBoardService(不带历史缓存)"""
    data_dir = tmp_path / "reports"
    monkeypatch.setattr(rbs, "get_settings", lambda: _FakeSettings(str(data_dir)))
    return ReportBoardService()


def test_save_writes_frontmatter_and_content(service):
    """落盘内容:frontmatter 元数据(title/source/url/analyzed_at/pushed_at)+ 正文"""
    saved = service.save_report(
        title="2026-09-23 A股宏观展望｜偏支撑｜相对利于成长",
        content="# 核心判断\n利多成长板块。",
        source=SOURCE_A,
        url="https://example.com/report",
    )

    assert saved.duplicate is False
    path = service._data_dir / f"{saved.report_id}.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert f"title: 2026-09-23 A股宏观展望｜偏支撑｜相对利于成长" in text
    assert f"source: {SOURCE_A}" in text
    assert "url: https://example.com/report" in text
    assert "analyzed_at: 2026-09-23" in text  # 从标题开头提取
    assert "pushed_at: " in text
    assert text.count("---") >= 2  # frontmatter 开闭
    assert "# 核心判断" in text


def test_save_idempotent_same_source_title(service):
    """同 (source, title) 二次推送:duplicate=True、返回已有 id、不新增文件"""
    first = service.save_report("2026-09-23 测试｜中性", "内容 v1", SOURCE_A)
    second = service.save_report("2026-09-23 测试｜中性", "内容 v2(重推)", SOURCE_A)

    assert second.duplicate is True
    assert second.report_id == first.report_id
    files = list(service._data_dir.glob("*.md"))
    assert len(files) == 1
    # 不覆盖写:内容以首次为准
    assert "内容 v1" in files[0].read_text(encoding="utf-8")


def test_save_rejects_source_outside_whitelist(service):
    """白名单外的 source 拒绝(ValueError → 路由 400)"""
    with pytest.raises(ValueError, match="非法 source"):
        service.save_report("2026-09-23 t", "c", "evil-skill")


def test_save_rejects_empty_and_oversize(service):
    """空 content / 超长 content / 超长 title / 空 title 均拒绝"""
    with pytest.raises(ValueError, match="content 不能为空"):
        service.save_report("2026-09-23 t", "   ", SOURCE_A)
    with pytest.raises(ValueError, match="content 超长"):
        service.save_report("2026-09-23 t", "x" * (rbs.MAX_CONTENT_LEN + 1), SOURCE_A)
    with pytest.raises(ValueError, match="title 超长"):
        service.save_report("t" * 201, "c", SOURCE_A)
    with pytest.raises(ValueError, match="title 不能为空"):
        service.save_report("  ", "c", SOURCE_A)


def test_list_reports_sorted_desc_and_filter(service):
    """列表按 analyzed_at 倒序(再 pushed_at 倒序);source 筛选生效"""
    service.save_report("2026-09-21 早的", "c1", SOURCE_A)
    service.save_report("2026-09-23 晚的A", "c2", SOURCE_A)
    service.save_report("2026-09-22 债市", "c3", SOURCE_B)

    metas = service.list_reports()
    assert [m.analyzed_at for m in metas] == ["2026-09-23", "2026-09-22", "2026-09-21"]
    assert {m.source for m in metas} == {SOURCE_A, SOURCE_B}

    only_a = service.list_reports(source=SOURCE_A)
    assert [m.title for m in only_a] == ["2026-09-23 晚的A", "2026-09-21 早的"]

    only_b = service.list_reports(source=SOURCE_B)
    assert [m.title for m in only_b] == ["2026-09-22 债市"]


def test_list_reports_empty_dir(service):
    """空目录/目录不存在 → 空列表不报错"""
    assert service.list_reports() == []


def test_get_report_unknown_returns_none(service):
    """未知 id / 非法 id → None(路由 404)"""
    service.save_report("2026-09-23 t", "c", SOURCE_A)
    assert service.get_report("2099-01-01-no-such-0000000") is None
    # 路径穿越形态的 id 直接判非法
    assert service.get_report("..%2F..%2Fetc") is None


def test_report_id_only_safe_characters(service):
    """report_id 只含 [0-9a-zA-Z-],杜绝路径穿越"""
    saved = service.save_report(
        "2026-09-23 a/b:c|d 特殊字符", "c", SOURCE_A, url="x"
    )
    assert saved.report_id == "".join(
        ch for ch in saved.report_id if ch.isalnum() or ch == "-"
    )
    assert "/" not in saved.report_id and "\\" not in saved.report_id
    # 文件确实落在数据目录内(一级,无子目录穿越)
    assert saved.path.startswith(str(service._data_dir))


def test_save_title_without_date_uses_today(service):
    """标题提取不到 YYYY-MM-DD → analyzed_at 用推送当日"""
    saved = service.save_report("无日期标题", "c", SOURCE_A)
    meta = service.list_reports()[0]
    assert saved.report_id.startswith(meta.analyzed_at)
    assert len(meta.analyzed_at) == 10
    assert meta.analyzed_at[4] == "-" and meta.analyzed_at[7] == "-"
