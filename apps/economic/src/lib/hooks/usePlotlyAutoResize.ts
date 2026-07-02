/**
 * Plotly auto-resize hook — 修复 hidden 容器首次 newPlot width=0 的兼容问题
 *
 * ## 背景
 * 切 tab 用 `<div hidden>` 替代条件渲染（详见 plan polymorphic-wiggling-lollipop.md 方案 2），
 * 7 个 Tab 始终挂载。react-plotly.js 的 Plot 组件首次 mount 时调 Plotly.newPlot(graphDiv, ...)。
 *
 * 此时如果父容器是 `display:none`（即 hidden），graphDiv 的 width=0，Plotly 回退到默认 700px。
 * 后续即使父容器变 visible（display:block），react-plotly.js 的 useResizeHandler 只监听
 * window 'resize' 事件、不监听 display 变化，所以图表卡在 700px → 用户看到"图很窄"。
 *
 * ## 解决
 * 用 callback ref 拿到容器元素，再用 ResizeObserver 监听尺寸变化。当宽度从
 * < 50px（hidden 状态）跳到 ≥ 100px（visible）时，主动调 Plotly.Plots.resize(graphDiv)
 * 强制重测。
 *
 * ## 为什么用 callback ref
 * ComparisonChart 等组件在 `selectedIds.length === 0` 时显示空状态、不渲染 Plot。
 * 用 useRef 时，useEffect 在 mount 时跑一次，那时元素可能是空状态分支的 div，
 * 之后切换到 Plot 分支时元素被替换，但 useEffect 不会重跑。
 * callback ref 模式：每次 DOM 元素变化（包括 null → div、div → div'）都触发 effect 重新 setup。
 *
 * ## 关键实现点
 * Plotly 实例**不**通过 window 全局暴露（react-plotly.js 闭包持有），所以必须动态 import
 * `plotly.js/dist/plotly.js` 拿到真实模块（主入口走 src/，需要 buffer 等 Node polyfill，
 * 浏览器端无法解析）。dist 版本已被 react-plotly.js 打入 bundle，动态 import 走缓存不增体积。
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

import { useCallback, useEffect, useState } from 'react';

type PlotlyModule = {
  Plots: {
    resize: (gd: HTMLElement) => void;
  };
};

export function usePlotlyAutoResize<T extends HTMLElement>() {
  const [el, setEl] = useState<T | null>(null);

  useEffect(() => {
    if (!el) return;

    // 动态 import 拿 Plotly 实例（react-plotly.js 不暴露到 window）
    let plotlyPromise: Promise<PlotlyModule> | null = null;
    let cancelled = false;
    const getPlotly = () => {
      if (!plotlyPromise) {
        plotlyPromise = import('plotly.js/dist/plotly.js').then(
          (m) => (m.default ?? m) as PlotlyModule
        );
      }
      return plotlyPromise;
    };

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
        getPlotly().then((Plotly) => {
          if (cancelled) return;
          try {
            Plotly.Plots.resize(graphDiv);
          } catch {
            // Plotly 还未完全初始化，忽略（下次 ResizeObserver 触发还会再试）
          }
        });
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
      cancelled = true;
      ro.disconnect();
      clearTimeout(retryTimer);
    };
  }, [el]);

  // 返回 stable callback ref（useState 的 setter 在 React 18+ 是 stable 的）
  return setEl;
}
