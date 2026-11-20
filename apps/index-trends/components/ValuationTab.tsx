"use client";

/** 纯估值页：只做 PB/PE 分位的指数（如创业板50）用这个视图。
 *
 * 不渲染通道位置、通道图与模型选择——该指数没有走势通道。
 */
import { useEffect, useState } from "react";
import ValuationBlock from "./ValuationBlock";
import { api } from "../lib/api";
import type { Valuation } from "../lib/types";

interface Props {
  code: string;
  reloadKey: number;
}

export default function ValuationTab({ code, reloadKey }: Props) {
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .valuation(code)
      .then((data) => {
        if (cancelled) return;
        setValuation(data);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [code, reloadKey, retryTick]);

  return (
    <section>
      {!valuation && !error && <div className="message">加载中…</div>}
      {error && (
        <div className="message error">
          加载失败：{error}
          <br />
          <button className="retry-btn" onClick={() => setRetryTick((t) => t + 1)}>
            重试
          </button>
        </div>
      )}

      {valuation && (
        <div className="status-card">
          <ValuationBlock code={code} valuation={valuation} reloadKey={reloadKey + retryTick} />
        </div>
      )}

      <div className="notes">
        <div className="note-item">
          该指数只做估值分位，不提供走势通道：没有行情采集、没有通道位置、
          也没有趋势延伸。
        </div>
        <div className="note-item">
          PB / PE-TTM 近10年分位来自理杏仁（总市值加权），是
          <span className="emphasis">独立的估值口径</span>。口径以 PB 为主：
          创业板盈利波动大，PE 的分母不稳；PE 用来交叉验证。
        </div>
      </div>
    </section>
  );
}
