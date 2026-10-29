"use client";

/** 当前通道 Tab：近10年 / 成立以来模型切换 + 状态摘要 + 主图（含趋势延伸）。 */
import { useEffect, useState } from "react";
import TrendChart from "./TrendChart";
import { api } from "../lib/api";
import {
  KIND_LABELS,
  REGION_LABELS,
  type ChartData,
  type CurrentStatus,
  type ModelInfo,
} from "../lib/types";

export type CurrentModel = "trailing_120m" | "since_inception";

interface CurrentTabProps {
  selected: CurrentModel;
  onSelect: (model: CurrentModel) => void;
  onGoHistory: () => void;
}

interface TabState {
  status: CurrentStatus | null;
  chart: ChartData | null;
  error: string | null;
  loading: boolean;
}

export default function CurrentTab({ selected, onSelect, onGoHistory }: CurrentTabProps) {
  const [state, setState] = useState<TabState>({
    status: null,
    chart: null,
    error: null,
    loading: true,
  });

  const [retryTick, setRetryTick] = useState(0); // 重试用：URL 不变时也强制重跑加载

  useEffect(() => {
    let cancelled = false;
    setState({ status: null, chart: null, error: null, loading: true });
    // 切换模型后全部数值重新取自所选模型，不混用缓存；
    // chart 用 kind: 简写由后端解析为该模型最新版本
    Promise.all([api.status(selected), api.chart(`kind:${selected}`, "current")])
      .then(([status, chart]) => {
        if (!cancelled) setState({ status, chart, error: null, loading: false });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({
            status: null,
            chart: null,
            error: err instanceof Error ? err.message : "加载失败",
            loading: false,
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selected, retryTick]);

  const model: ModelInfo | null =
    state.chart?.model ?? state.status?.model ?? null;

  return (
    <section>
      <div className="picker" role="tablist" aria-label="当前模型选择">
        {(["trailing_120m", "since_inception"] as const).map((kind) => (
          <button
            key={kind}
            aria-current={selected === kind}
            onClick={() => onSelect(kind)}
          >
            {KIND_LABELS[kind]}
          </button>
        ))}
      </div>

      {state.loading && <div className="message">加载中…</div>}
      {state.error && (
        <div className="message error">
          加载失败：{state.error}
          <br />
          <button className="retry-btn" onClick={() => setRetryTick((t) => t + 1)}>
            重试
          </button>
        </div>
      )}

      {state.status && !state.status.available && (
        <div className="empty">
          模型尚未就绪（{state.status.reason === "model_not_ready" ? "还没有可用的通道模型，等待首次数据刷新" : "暂无日线数据"}）。
          <br />
          服务首次启动后需要一次数据刷新。
        </div>
      )}

      {state.status?.available && model && (
        <>
          <div className="status-card">
            <div className="close-line">
              <small style={{ color: "#8c6847" }}>最近已完成交易日收盘</small>
              <b>{state.status.close?.toFixed(2)}</b>
              <small>{state.status.price_as_of}</small>
            </div>
            <div className="position-line">
              <small style={{ color: "#8c6847" }}>通道位置</small>
              <b>{state.status.position_pct?.toFixed(1)}%</b>
              <span className={`region-badge region-${state.status.region}`}>
                {REGION_LABELS[state.status.region ?? "middle"]}
              </span>
            </div>
            <div className="tracks-line">
              上轨 {state.status.upper?.toFixed(0)} / 中线 {state.status.mid?.toFixed(0)} / 下轨{" "}
              {state.status.lower?.toFixed(0)}
              <br />
              投影月 {state.status.projection_month}
            </div>
            <div className="model-line">
              模型：{KIND_LABELS[selected]}（{model.fit_start} – {model.fit_end}，{model.months}
              个月）
              <br />
              版本 {model.algorithm_version} · 数据截至 {model.data_cutoff_month} ·{" "}
              {new Date(model.calculated_at).toLocaleString("zh-CN")}
            </div>
          </div>

          {state.chart && (
            <div className="chart-card">
              <TrendChart data={state.chart} chartId={`current-${selected}`} />
              <div className="range-note">
                <span>
                  拟合区间 {state.chart.model.fit_start} – {state.chart.model.fit_end}
                </span>
                <span>拟合截止 {state.chart.fit_boundary_month}</span>
                {state.chart.extend_note && <span>{state.chart.extend_note}</span>}
              </div>
            </div>
          )}

          <div className="weekly-hint">
            📬 每周五 19:00（北京时间）发送一次通道位置摘要，模型为独立持久化配置，
            与本页临时切换互不影响；当前页面的虚线延伸仅为趋势投影，不是目标价。
            <button
              onClick={onGoHistory}
              style={{
                background: "transparent",
                color: "#c56722",
                border: "none",
                padding: 0,
                font: "inherit",
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              查看历史回溯 →
            </button>
          </div>

          <div className="notes">
            <div className="note-item">
              「近10年」= 最近 120 个完整自然月；「成立以来」= 2005-04 至最近完整月。
              新的完整月结束后模型自动重算出新版本，同一月内价格波动不改变模型。
            </div>
            <div className="note-item">
              通道位置 = (收盘 − 下轨) ÷ (上轨 − 下轨) × 100。区域阈值 25/75
              仅为阅读分层，<span className="emphasis">不是买卖阈值</span>；
              「低位」不等于低估，上轨突破也不等于应当卖出。
            </div>
          </div>
        </>
      )}
    </section>
  );
}
