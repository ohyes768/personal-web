"use client";

/** 宽基趋势观察主页面：历史回溯 / 当前通道两个 Tab。
 *
 * Tab、窗口、模型都编码在 URL 查询参数（tab/window/model），
 * 刷新和返回不换图；图表懒加载由 Tab 组件各自负责。
 */
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import CurrentTab, { type CurrentModel } from "../components/CurrentTab";
import HistoryTab from "../components/HistoryTab";
import { api } from "../lib/api";
import type { DataStatus, HistoryOverview } from "../lib/types";

type Tab = "history" | "current";

function DataStatusBar({ status }: { status: DataStatus | null }) {
  if (!status) return null;
  return (
    <div className="data-status">
      {status.state === "empty" && (
        <span className="stale">暂无数据：等待首次刷新</span>
      )}
      {status.state === "stale" && (
        <span className="stale">
          数据可能过期：截至 {status.data_cutoff_month}（期望{" "}
          {status.expected_cutoff_month}）
        </span>
      )}
      {status.provider && <span>来源 {status.provider}</span>}
      {status.daily_last_date && <span>日线 {status.daily_last_date}</span>}
      {status.captured_at && (
        <span>抓取 {new Date(status.captured_at).toLocaleString("zh-CN")}</span>
      )}
    </div>
  );
}

function PageInner() {
  const router = useRouter();
  const params = useSearchParams();
  const tab: Tab = params.get("tab") === "current" ? "current" : "history";
  const windowParam = params.get("window") ?? "";
  const modelParam: CurrentModel =
    params.get("model") === "since_inception" ? "since_inception" : "trailing_120m";

  const [overview, setOverview] = useState<HistoryOverview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // 重试与「获取最新」成功后重载
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  // 历史窗口默认取第一个；默认值不写进 URL，保持地址干净
  const selectedWindow =
    windowParam && (overview?.windows.some((w) => w.stable_id === windowParam) || windowParam === "all")
      ? windowParam
      : (overview?.windows[0]?.stable_id ?? "");

  const setQuery = useCallback(
    (patch: Record<string, string>) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      router.replace(`?${next.toString()}`, { scroll: false });
    },
    [params, router],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .history()
      .then((data) => {
        if (!cancelled) {
          setOverview(data);
          setOverviewError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setOverviewError(err instanceof Error ? err.message : "加载失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    setRefreshNote(null);
    setRefreshError(null);
    api
      .refresh()
      .then((result) => {
        setRefreshNote(result.message);
        setTick((t) => t + 1);
      })
      .catch((err: unknown) => {
        setRefreshError(err instanceof Error ? err.message : "获取失败");
      })
      .finally(() => setRefreshing(false));
  }, []);

  return (
    <main>
      <header className="site">
        <div className="site-top">
          <div>
            <div className="eyebrow">宽基趋势观察 · INDEX TRENDS</div>
            <h1>沪深300 · 线性回归通道</h1>
          </div>
          <button type="button" className="refresh" disabled={refreshing} onClick={onRefresh}>
            {refreshing ? "正在获取…" : "获取最新"}
          </button>
        </div>
        <p className="subtitle">
          月收盘拟合的长期趋势通道，回看它在历史上的表现，观察当前指数位置。
          描述相对趋势的位置，不构成买卖建议。
        </p>
      </header>

      {refreshNote && <div className="message">{refreshNote}</div>}
      {refreshError && <div className="message error">获取失败：{refreshError}</div>}

      <nav className="tabs" aria-label="页面切换">
        <button aria-current={tab === "history"} onClick={() => setQuery({ tab: "history", window: windowParam })}>
          历史回溯
        </button>
        <button aria-current={tab === "current"} onClick={() => setQuery({ tab: "current", model: modelParam })}>
          当前通道
        </button>
      </nav>

      <DataStatusBar status={overview?.data_status ?? null} />

      {overviewError && (
        <div className="message error">
          数据加载失败：{overviewError}
          <br />
          <button className="retry-btn" onClick={() => setTick((t) => t + 1)}>
            重试
          </button>
        </div>
      )}

      {tab === "history" &&
        (overview ? (
          <HistoryTab
            overview={overview}
            selected={selectedWindow}
            reloadKey={tick}
            onSelect={(stableId) => setQuery({ tab: "history", window: stableId })}
          />
        ) : (
          !overviewError && <div className="message">加载中…</div>
        ))}

      {tab === "current" && (
        <CurrentTab
          selected={modelParam}
          reloadKey={tick}
          onSelect={(model) => setQuery({ tab: "current", model })}
          onGoHistory={() => setQuery({ tab: "history", window: "" })}
        />
      )}
    </main>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<main>加载中…</main>}>
      <PageInner />
    </Suspense>
  );
}
