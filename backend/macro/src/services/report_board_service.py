"""分析报告看板服务

接收 impact skill 推送的 markdown 分析报告,落盘为 frontmatter + 正文的 .md 文件,
供前端报告看板浏览。无数据库,文件系统存储(对齐 macro_signal_service 模式)。
"""
import hashlib
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

from src.config import get_settings
from src.models import ReportDetail, ReportMeta
from src.utils.logger import setup_logger

logger = setup_logger("report_board_service")

# 报告来源白名单(两个 impact skill)
ALLOWED_SOURCES = {
    "a-share-macro-impact-skill",
    "bond-market-macro-impact-skill",
}

MAX_TITLE_LEN = 200
MAX_CONTENT_LEN = 200_000

# report_id 仅允许安全字符(拼入文件路径,防路径穿越)
SAFE_ID_PATTERN = re.compile(r"[^0-9a-zA-Z-]")

# 标题开头 YYYY-MM-DD(分析日期)
TITLE_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")


class SavedReport(NamedTuple):
    """save_report 结果(不可变)"""

    report_id: str
    path: str
    duplicate: bool


class ReportBoardService:
    """单例服务(列表索引内存缓存,目录 mtime 失效)"""

    def __init__(self):
        self.settings = get_settings()
        self._index_cache: Optional[Tuple[float, List[ReportMeta]]] = None

    @property
    def _data_dir(self) -> Path:
        return Path(self.settings.macro_report_data_dir)

    # --- 写入 ---

    def save_report(self, title: str, content: str, source: str, url: str = "") -> SavedReport:
        """校验 → 幂等检查 → 原子写。违例抛 ValueError(路由层转 400)。"""
        if source not in ALLOWED_SOURCES:
            raise ValueError(f"非法 source: {source}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title 不能为空")
        if len(title) > MAX_TITLE_LEN:
            raise ValueError(f"title 超长(最多 {MAX_TITLE_LEN} 字符)")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content 不能为空")
        if len(content) > MAX_CONTENT_LEN:
            raise ValueError(f"content 超长(最多 {MAX_CONTENT_LEN} 字符)")

        # 幂等:同 (source, title) 已存在 → 不覆盖写,返回已有 id
        # (强制重扫绕过缓存,避免目录 mtime 粒度导致漏检)
        for meta in self._scan_index():
            if meta.source == source and meta.title == title:
                return SavedReport(
                    report_id=meta.report_id,
                    path=str(self._data_dir / f"{meta.report_id}.md"),
                    duplicate=True,
                )

        analyzed_at = self._extract_analyzed_at(title)
        report_id = self._make_report_id(analyzed_at, source, title)
        path = self._data_dir / f"{report_id}.md"
        self._atomic_write_markdown(
            path,
            title=self._frontmatter_value(title),
            source=source,
            url=self._frontmatter_value(url or ""),
            analyzed_at=analyzed_at,
            content=content,
        )
        self.clear_cache()
        logger.info(f"报告已写入: {path} ({path.stat().st_size} bytes)")
        return SavedReport(report_id=report_id, path=str(path), duplicate=False)

    @staticmethod
    def _extract_analyzed_at(title: str) -> str:
        """分析日期 = 标题开头 YYYY-MM-DD;提取不到(或非法日期)用推送当日"""
        m = TITLE_DATE_PATTERN.match(title.strip())
        if m:
            try:
                date.fromisoformat(m.group(1))
                return m.group(1)
            except ValueError:
                pass
        return date.today().isoformat()

    @staticmethod
    def _make_report_id(analyzed_at: str, source: str, title: str) -> str:
        """{analyzed_at}-{source}-{sha1(source+title) 前 8 位};仅保留 [0-9a-zA-Z-] 防路径穿越"""
        slug = hashlib.sha1((source + title).encode("utf-8")).hexdigest()[:8]
        return SAFE_ID_PATTERN.sub("", f"{analyzed_at}-{source}-{slug}")

    @staticmethod
    def _frontmatter_value(value: str) -> str:
        """frontmatter 值单行化(换行会破坏 key: value 行格式)"""
        return value.replace("\r", " ").replace("\n", " ").strip()

    @staticmethod
    def _atomic_write_markdown(
        path: Path, title: str, source: str, url: str, analyzed_at: str, content: str
    ) -> None:
        """原子写 markdown(frontmatter + 正文):临时文件 + replace,避免半写被读到"""
        path.parent.mkdir(parents=True, exist_ok=True)
        pushed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        frontmatter = (
            "---\n"
            f"title: {title}\n"
            f"source: {source}\n"
            f"url: {url}\n"
            f"analyzed_at: {analyzed_at}\n"
            f"pushed_at: {pushed_at}\n"
            "---\n"
        )
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(frontmatter + "\n" + content)
        tmp_path.replace(path)

    # --- 读取 ---

    def list_reports(self, source: Optional[str] = None) -> List[ReportMeta]:
        """报告列表:analyzed_at 倒序、再 pushed_at 倒序;source 可选筛选"""
        metas = self._get_index()
        if source is not None:
            metas = [m for m in metas if m.source == source]
        return metas

    def get_report(self, report_id: str) -> Optional[ReportDetail]:
        """单篇详情(含正文);id 非法或文件不存在返回 None"""
        if not isinstance(report_id, str) or not report_id or SAFE_ID_PATTERN.search(report_id):
            return None
        parsed = self._parse_report_file(self._data_dir / f"{report_id}.md")
        if parsed is None:
            return None
        fields, content = parsed
        return ReportDetail(report_id=report_id, **fields, content=content)

    def delete_report(self, report_id: str) -> bool:
        """删除单篇报告文件;id 非法或文件不存在返回 False(路由层转 404)"""
        if not isinstance(report_id, str) or not report_id or SAFE_ID_PATTERN.search(report_id):
            return False
        path = self._data_dir / f"{report_id}.md"
        try:
            path.unlink()
        except OSError:
            return False
        self.clear_cache()
        logger.info(f"报告已删除: {path}")
        return True

    def _get_index(self) -> List[ReportMeta]:
        """索引缓存:目录 mtime 变化才重扫"""
        try:
            dir_mtime = self._data_dir.stat().st_mtime
        except OSError:
            return []
        if self._index_cache is not None and self._index_cache[0] == dir_mtime:
            return self._index_cache[1]
        metas = self._scan_index()
        self._index_cache = (dir_mtime, metas)
        return metas

    def _scan_index(self) -> List[ReportMeta]:
        if not self._data_dir.is_dir():
            return []
        metas: List[ReportMeta] = []
        for path in self._data_dir.glob("*.md"):
            parsed = self._parse_report_file(path)
            if parsed is not None:
                fields, _ = parsed
                metas.append(ReportMeta(report_id=path.stem, **fields))
        metas.sort(key=lambda m: (m.analyzed_at, m.pushed_at), reverse=True)
        return metas

    @staticmethod
    def _parse_report_file(path: Path) -> Optional[Tuple[Dict[str, str], str]]:
        """解析自家格式的 frontmatter(每行 'key: value')+ 正文;损坏/缺 frontmatter 返回 None"""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if not text.startswith("---"):
            return None
        lines = text.split("\n")
        fields: Dict[str, str] = {}
        i = 1
        closed = False
        while i < len(lines):
            line = lines[i].rstrip("\r")
            if line.strip() == "---":
                closed = True
                break
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
            i += 1
        if not closed:
            return None
        content = "\n".join(lines[i + 1:]).lstrip("\n")
        meta = {
            "title": fields.get("title", ""),
            "source": fields.get("source", ""),
            "url": fields.get("url", ""),
            "analyzed_at": fields.get("analyzed_at", ""),
            "pushed_at": fields.get("pushed_at", ""),
        }
        return meta, content

    def clear_cache(self) -> None:
        """清空索引缓存(写入后调用)"""
        self._index_cache = None


_singleton: Optional[ReportBoardService] = None


def get_report_board_service() -> ReportBoardService:
    global _singleton
    if _singleton is None:
        _singleton = ReportBoardService()
    return _singleton
