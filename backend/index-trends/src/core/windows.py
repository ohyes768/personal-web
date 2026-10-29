"""固定历史窗口生成：120 个月窗口、36 个月步进。

样本不足 120 个月时窗口数为 0；下一窗口在样本足够后才产生，
不提前采用未完成的窗口。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.core.months import shift_month

WINDOW_MONTHS = 120
STEP_MONTHS = 36
OBSERVATION_MONTHS = 36  # 拟合后最多展示 36 个月后续价格，模型保持不变


@dataclass(frozen=True)
class FixedWindow:
    window: int
    start_month: str
    end_month: str          # 拟合截止月（含）
    observation_end_month: str  # 后续观察区截止月（不足 36 个月时按实际可用，可为 None）

    @property
    def stable_id(self) -> str:
        """稳定标识：用拟合起点命名，数据更新不变。"""
        return f"fixed-{self.start_month}"


def generate_fixed_windows(months: list[str]) -> list[FixedWindow]:
    """从连续月序列生成全部固定窗口。

    months 为升序完整月序列；最后一个窗口拟合完后样本不足 36 个月时，
    observation_end_month 为实际最后一个月（或 None 表示暂无后续月）。
    """
    total = len(months)
    if total < WINDOW_MONTHS:
        return []
    last_month = months[-1]
    windows: list[FixedWindow] = []
    for start_idx in range(0, total - WINDOW_MONTHS + 1, STEP_MONTHS):
        start_month = months[start_idx]
        end_month = shift_month(start_month, WINDOW_MONTHS - 1)
        obs_end_idx = start_idx + WINDOW_MONTHS - 1 + OBSERVATION_MONTHS
        observation_end = months[obs_end_idx] if obs_end_idx < total else last_month if start_idx + WINDOW_MONTHS - 1 < total - 1 else None
        windows.append(
            FixedWindow(
                window=len(windows) + 1,
                start_month=start_month,
                end_month=end_month,
                observation_end_month=observation_end,
            )
        )
    return windows
