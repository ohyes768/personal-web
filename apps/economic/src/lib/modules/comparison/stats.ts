/**
 * 对比模块统计工具
 * - rollingCorrelation: 滚动窗口 Pearson 相关系数，用于「双轴+相关性」模式子图
 */

/**
 * 滚动 Pearson 相关系数
 *
 * @param xs 第一条曲线（与 dates 对齐，可含 null）
 * @param ys 第二条曲线（与 dates 对齐，可含 null）
 * @param window 滑动窗口（按数组索引，默认 30）
 * @returns 与 dates 等长的数组；窗口内有效样本 < minSamples 时为 null
 *
 * 算法：
 * - 窗口 [i-window+1, i]，仅当 xs[k] 和 ys[k] 都非 null 才计入样本
 * - 样本数 < 10 → null（避免小样本不稳定）
 * - Pearson: r = Σ((x-x̄)(y-ȳ)) / √(Σ(x-x̄)² · Σ(y-ȳ)²)
 * - 分母为 0（某条线在窗口内恒定）→ null
 */
export function rollingCorrelation(
  xs: (number | null)[],
  ys: (number | null)[],
  window = 30,
  minSamples = 10,
): (number | null)[] {
  const n = Math.min(xs.length, ys.length);
  const result: (number | null)[] = new Array(n).fill(null);

  if (window < minSamples || n < minSamples) return result;

  for (let i = window - 1; i < n; i++) {
    const start = i - window + 1;
    const xslice: number[] = [];
    const yslice: number[] = [];
    for (let k = start; k <= i; k++) {
      const x = xs[k];
      const y = ys[k];
      if (x != null && y != null && !Number.isNaN(x) && !Number.isNaN(y)) {
        xslice.push(x);
        yslice.push(y);
      }
    }
    if (xslice.length < minSamples) continue;

    const m = xslice.length;
    const xMean = xslice.reduce((s, v) => s + v, 0) / m;
    const yMean = yslice.reduce((s, v) => s + v, 0) / m;

    let num = 0;
    let dx2 = 0;
    let dy2 = 0;
    for (let k = 0; k < m; k++) {
      const dx = xslice[k] - xMean;
      const dy = yslice[k] - yMean;
      num += dx * dy;
      dx2 += dx * dx;
      dy2 += dy * dy;
    }
    const den = Math.sqrt(dx2 * dy2);
    if (den === 0) continue;
    result[i] = num / den;
  }

  return result;
}
