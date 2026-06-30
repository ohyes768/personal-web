/**
 * Plotly auto-resize hook — 修复 hidden 容器首次 newPlot width=0 的兼容问题
 *
 * ## 背景
 * 切 tab 用 `<div hidden>` 替代条件渲染（详见 plan polymorphic-wiggling-lollipop.md 方案 2），
 * 7 个 Tab 始终挂载。react-plotly.js 的 Plot 组件首次 mount 时调 Plotly.newPlot(graphDiv, ...)。
 *
 * 此时如果父容器是 `display:none`（即 hidden），graphDiv 的 width=0，Plotly 用 0 宽 newPlot。
 * 后续即使父容器变 visible（display:block），react-plotly.js 的 useResizeHandler 不会触发
 * 完整 relayout，图表保留 0 宽 → 用户看到"曲线图这么窄"。
 *
 * ## 解决
 * 用 ResizeObserver 监听容器尺寸变化。当宽度从 < 50px（hidden 状态）跳到 ≥ 100px（visible）
 * 时，主动调 Plotly.Plots.resize(graphDiv) 强制重测。
 *
 * ## 用法
 * ```tsx
 * const containerRef = usePlotlyAutoResize<HTMLDivElement>();
 * return (
 *   <div ref={containerRef}>
 *     <Plot data={...} layout={...} config={...} />
 *   </div>
 * );
 * ```
 *
 * 必须把容器 ref 放在外层 div，react-plotly.js 的 Plot 组件挂在它里面，
 * 内部通过 `js-plotly-plot` className 找 graphDiv。
 */
'use client';

import { useEffect, useRef } from 'react';

declare global {
  interface Window {
    Plotly?: {
      Plots: {
        resize: (gd: HTMLElement) => void;
      };
    };
  }
}

export function usePlotlyAutoResize<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    let lastWidth = 0;

    const findGraphDiv = (): HTMLElement | null => {
      return el.querySelector('.js-plotly-plot') as HTMLElement | null;
    };

    const tryResize = () => {
      const graphDiv = findGraphDiv();
      if (!graphDiv) return;
      const rect = graphDiv.getBoundingClientRect();
      // 仍然 hidden（width=0 或很小），不调
      if (rect.width < 50) {
        lastWidth = rect.width;
        return;
      }
      // hidden → visible 切换（lastWidth < 50, now >= 100），强制 resize
      if (lastWidth < 50 && rect.width >= 100) {
        try {
          window.Plotly?.Plots?.resize(graphDiv);
        } catch {
          // Plotly 还未完全初始化，忽略（下次 ResizeObserver 触发还会再试）
        }
      }
      lastWidth = rect.width;
    };

    const ro = new ResizeObserver(() => {
      tryResize();
    });
    ro.observe(el);

    // 首次尝试（处理 Plot 组件挂载晚于本 effect 的竞态）
    tryResize();
    const retryTimer = setTimeout(tryResize, 200);

    return () => {
      ro.disconnect();
      clearTimeout(retryTimer);
    };
  }, []);

  return ref;
}