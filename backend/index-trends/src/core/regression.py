"""线性回归通道计算（算法版本 lrc-ltb-port-v1）。

纯计算层：不依赖网络、FastAPI、第三方数值库。

公式（月序号 x 从 0 起，等间距）：
    mid(x)  = a + b * x                OLS 中线
    deviation = sqrt(mean((y[x] - (a + b * (x + 1)))^2))
    upper/lower = mid ± multiplier * deviation

deviation 的基线前移一根 K 线是公开移植公式（LonesomeTheBlue Linear
Regression Channel）的实现细节，与本版本绑定；若改为标准残差 RMSE 必须
另升算法版本，不能悄悄替换后仍宣称同一条通道。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

ALGORITHM_VERSION = "lrc-ltb-port-v1"
DEFAULT_MULTIPLIER = 2.0


@dataclass(frozen=True)
class Coefficients:
    slope: float
    intercept: float
    deviation: float


def fit_channel(closes: list[float], multiplier: float = DEFAULT_MULTIPLIER) -> Coefficients:
    """对一段连续月收盘拟合通道。

    closes 必须全部为有限正数；窗口长度由调用方保证（校验在外层）。
    """
    n = len(closes)
    if n == 0:
        raise ValueError("收盘序列为空")
    if not all(math.isfinite(c) and c > 0 for c in closes):
        raise ValueError("收盘序列含非有限或非正数值")
    if multiplier <= 0 or not math.isfinite(multiplier):
        raise ValueError("通道宽度参数必须为正数")

    mean_x = (n - 1) / 2
    mean_y = sum(closes) / n
    sxx = sum((x - mean_x) ** 2 for x in range(n))
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(closes))
    if sxx == 0:
        raise ValueError("序列长度不足，无法拟合")
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    variance = sum(
        (y - (intercept + slope * (x + 1))) ** 2 for x, y in enumerate(closes)
    ) / n
    deviation = math.sqrt(variance)
    if not math.isfinite(deviation) or deviation <= 0:
        raise ValueError("通道宽度无效（deviation 非正），模型无效")
    return Coefficients(slope=slope, intercept=intercept, deviation=deviation)


def channel_at(coeff: Coefficients, x: float, multiplier: float = DEFAULT_MULTIPLIER) -> tuple[float, float, float]:
    """投影序号 x 处的 (mid, upper, lower)。拟合结束后系数固定，仅 x 后移。"""
    mid = coeff.intercept + coeff.slope * x
    band = multiplier * coeff.deviation
    return mid, mid + band, mid - band
