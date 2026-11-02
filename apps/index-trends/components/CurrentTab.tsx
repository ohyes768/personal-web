"use client";

/** 当前通道 Tab：近10年 / 成立以来模型切换 + 状态摘要 + 主图（含约 1 年趋势延伸）。 */
import { useEffect, useState } from "react";
import TrendChart from "./TrendChart";
import { api } from "../lib/api";
import {
  KIND_LABELS,
  REGION_LABELS,
  type ChartData,
  type CurrentModelKind,
  type CurrentStatus,
  type ModelInfo,
} from "../lib/types";

export type CurrentModel = CurrentModelKind;

const MODEL_KINDS: CurrentModelKind[] = ["trailing_10y_weekly", "since_inception_weekly"];

interface CurrentTabProps {
  selected: CurrentModel;
  onSelect: (model: CurrentModel) => void;
  onGoHistory: () => void;
  reloadKey: number;
}

interface TabState {
  status: CurrentStatus | null;
  chart: ChartData | null;
  error: string | null;
  loading: boolean;
}

/** 摘要与图形必须来自同一份快照；版本不一致时重新取同一个模型，避免混画。 */
async function loadConsistent(model: CurrentModel): Promise<{
  status: CurrentStatus;
  chart: ChartData;
}> {
  let last: { status: CurrentStatus; chart: ChartData } | null = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const [status, chart] = await Promise.all([
      api.status(model),
      api.chart(`kind:${model}`, "current"),
    ]);
    last = { status, chart };
    const s = status.snapshot_id;
    const c = chart.snapshot_id;
    // 后端未提供 snapshot_id 时无法核对，按后端返回的单一版本使用
    if (!s || !c || s === c) return last;
  }
  throw new Error("数据版本不一致：摘要与图表来自不同快照，请重试");
}

export default function CurrentTab({ selected, onSelect, onGoHistory, reloadKey }: CurrentTabProps) {
  const [state, setState] = useState<TabState>({
    status: null,
    chart: null,
    error: null,
    loading: true,
  });

  const [retryTick, setRetryTick] = useState(0); // 重试用：URL 不变时也强制重跑加载

  useEffect(() => {
    let cancelled = false;
    // 切换模型后清空旧摘要，全部数值重新取自所选模型，不混用缓存
    setState({ status: null, chart: null, error: null, loading: true });
    // chart 用 kind: 简写由后端解析为该模型最新版本
    loadConsistent(selected)
      .then(({ status, chart }) => {
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
  }, [selected, retryTick, reloadKey]);

  const model: ModelInfo | null =
    state.chart?.model ?? state.status?.model ?? null;

  const dataState = state.status?.data_status?.state ?? "ok";
  const stale = dataState === "stale";

  return (
    <section>
      <div className="picker" role="tablist" aria-label="当前模型选择">
        {MODEL_KINDS.map((kind) => (
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
          模型尚未就绪（{state.status.reason === "model_not_ready" ? "还没有可用的通道模型，等待首次数据刷新" : "暂无周线数据"}）。
          <br />
          服务首次启动后需要一次数据刷新。
        </div>
      )}

      {state.status?.available && model && (
        <>
          {(stale || dataState === "error") && (
            <div className="message">
              {stale ? (
                <>
                  数据可能过期（缓存仍可读）：模型数据截至 {model.data_cutoff_week}
                  {state.status.data_status?.expected_cutoff_week
                    ? `，最近应完成周 ${state.status.data_status.expected_cutoff_week}`
                    : ""}
                  。请先执行「获取最新」。
                </>
              ) : (
                <>
                  数据异常
                  {state.status.data_status?.reason
                    ? `：${state.status.data_status.reason}`
                    : ""}
                  。以下数值来自最近一次成功快照，可能不是最新交易周。
                </>
              )}
            </div>
          )}

          <div className="status-card">
            <div className="close-line">
              <small style={{ color: "#8c6847" }}>最近收盘</small>
              <b>{state.status.close?.toFixed(2)}</b>
              <small>收盘日 {state.status.price_as_of}</small>
              {state.status.projection_week &&
                model.data_cutoff_week &&
                state.status.projection_week > model.data_cutoff_week && (
                  <small>该周进行中，不参与拟合</small>
                )}
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
              投影周 {state.status.projection_week}
            </div>
            <div className="model-line">
              模型：{KIND_LABELS[selected]}（{model.fit_start} – {model.fit_end}，{model.sample_count}
              个交易周）
              <br />
              版本 {model.algorithm_version} · 数据截至 {model.data_cutoff_week} · 末周收盘日{" "}
              {model.fit_last_trade_date} ·{" "}
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
                <span>拟合截止 {state.chart.fit_boundary_week}</span>
                {state.chart.extend_note && <span>{state.chart.extend_note}</span>}
              </div>
            </div>
          )}

          <div className="weekly-hint">
            📬 每周五 19:00（北京时间）发送一次通道位置摘要，模型为独立持久化配置，
            与本页临时切换互不影响；当前页面的虚线延伸约为 1 年，仅为趋势参考，不是目标价。
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
              「近10年」= 最近 10 个自然年内的完整交易周（样本数按实际有交易周计）；
              「成立以来」= 2005-04 至最近完整交易周。新的完整交易周结束后模型自动重算出新版本，
              同一周内价格波动不改变模型；进行中的周只展示，不参与拟合。
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
