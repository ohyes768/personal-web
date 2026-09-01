"""
CSV 导出：当前筛选结果 → UTF-8 BOM CSV
"""
import csv
import io
from datetime import date
from typing import Optional

from src.services.filter_service import FilterService

# 列名中文（PRD 验收）
CSV_COLUMNS = [
    ("code", "基金代码"),
    ("name", "基金名称"),
    ("fund_type", "基金类型"),
    ("size_yi", "规模(亿)"),
    ("age_years", "成立年限"),
    ("dd_3y", "近3年最大回撤(%)"),
    ("mgr_name", "基金经理"),
    ("mgr_company", "基金公司"),
    ("mgr_experience_years", "经理从业年限"),
    ("ret_1y", "近1年收益(%)"),
    ("ret_3y", "近3年收益(%)"),
    ("ret_5y", "近5年收益(%)"),
    ("rate_bond_pct", "利率债占比(%)"),
    ("fee_annual", "年费(%)"),
]


def export_csv(
    filters: dict,
    filter_service: FilterService,
) -> tuple[str, str]:
    """生成 CSV 内容 + 文件名。UTF-8 BOM 便于 Excel 直接打开。"""
    result = filter_service.screen(**filters)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in CSV_COLUMNS])
    for item in result["items"]:
        writer.writerow([_fmt(item.get(key)) for key, _ in CSV_COLUMNS])

    filename = f"funds_{date.today().strftime('%Y%m%d')}.csv"
    return buf.getvalue(), filename


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)
