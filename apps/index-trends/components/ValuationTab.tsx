"use client";

/** 纯估值页：只做 PB/PE 分位的指数（如创业板50）用这个视图。
 *
 * 不渲染通道位置、通道图与模型选择——该指数没有走势通道。
 */
import { useEffect, useState } from "react";
import PriceTrend from "./PriceTrend";
import ValuationBlock from "./ValuationBlock";
import { api } from "../lib/api";
import type { PriceSeries, Valuation } from "../lib/types";

interface Props {
  code: string;
  reloadKey: number;
  /** 该指数也有周线通道：同一个页面第三块 Tab，文案说清两套口径并列。 */
  hasChannel?: boolean;
}

export default function ValuationTab({ code, reloadKey, hasChannel = false }: Props) {
  const [valuation, setValuation] = useState<Valuation | null>(null);
  // 价格走势只在没有通道的指数上取：有通道时通道图已经表达了价格
  const [prices, setPrices] = useState<PriceSeries | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.valuation(code), hasChannel ? null : api.prices(code)])
      .then(([data, series]) => {
        if (cancelled) return;
        setValuation(data);
        setPrices(series);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [code, hasChannel, reloadKey, retryTick]);

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

      {!hasChannel && prices && prices.bars.length > 0 && (
        <div className="chart-card">
          <div className="close-line">
            <small style={{ color: "#8c6847" }}>最近收盘</small>
            <b>{prices.close?.toFixed(2)}</b>
            <small>收盘日 {prices.price_as_of}</small>
          </div>
          <PriceTrend series={prices} reloadKey={reloadKey + retryTick} />
          <div className="range-note">
            <span>
              周收盘 {prices.bars[0]?.date} – {prices.bars[prices.bars.length - 1]?.date}
            </span>
            <span>不拟合回归通道</span>
          </div>
        </div>
      )}

      {valuation && (
        <div className="status-card">
          <ValuationBlock code={code} valuation={valuation} reloadKey={reloadKey + retryTick} />
        </div>
      )}

      <div className="notes">
        <div className="note-item">
          {hasChannel
            ? "估值与通道是两套口径：通道位置看相对趋势通道的高低，分位看相对自身历史估值的贵贱，两者不必同时便宜或昂贵。"
            : "上图是周收盘价格走势（腾讯行情），下面两套是估值分位。该指数不拟合回归通道，所以没有通道位置、轨道与趋势延伸。"}
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
