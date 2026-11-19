"use client";

/** 通道图右侧的时间统计：50/40/30 线以下各待了多久、最长连续多久。
 *
 * 与图同源：都用 chart 接口返回的周收盘与轨道逐周算位置，切换模型或窗口时
 * 自动重算，不另存口径。条形长度就是停留占比，右边数字是同一件事的精确值。
 */
import { channelOccupancy } from "../lib/channelStats";
import type { ChartData } from "../lib/types";

/** 2023-02-06 → 2023/02 */
function monthOf(week: string): string {
  return week.slice(0, 7).replace("-", "/");
}

export default function OccupancyPanel({ data }: { data: ChartData }) {
  const occupancy = channelOccupancy(data.bars, data.fit_series, data.extension_series);
  if (occupancy.weeks === 0) return null;

  return (
    <aside className="occupancy" aria-label="通道位置停留时间">
      <p className="occupancy-head">
        线以下停留
        <span>{occupancy.weeks} 周</span>
      </p>

      {occupancy.stats.map((stat) => (
        <div className="occupancy-row" key={stat.threshold}>
          <p className="occupancy-line">
            <span>{stat.threshold}%</span>
            <b>{(stat.share * 100).toFixed(1)}%</b>
          </p>
          <div className="occupancy-bar" aria-hidden="true">
            <i style={{ width: `${stat.share * 100}%` }} />
          </div>
          <p className="occupancy-note">
            {stat.longest ? (
              <>
                最长 {stat.longest.weeks} 周
                <span className="occupancy-span">
                  {monthOf(stat.longest.start)}–{monthOf(stat.longest.end)}
                </span>
              </>
            ) : (
              "从未落入"
            )}
            {stat.current && <span className="occupancy-now">当前 {stat.current.weeks} 周</span>}
          </p>
        </div>
      ))}
    </aside>
  );
}
