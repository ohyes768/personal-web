/**
 * 夏普曲线纯 option 构造（不碰 DOM、不 import echarts）
 *
 * 与 components/sharpe-board/SharpeChart.tsx 的实例生命周期分开（design「前端设计」）。
 * 本文件必须保持零依赖：node --experimental-strip-types 测试直接执行（.ts 相对 import），
 * 不引 React、不引 echarts。
 *
 * 图合同（PRD R4 / implement 步骤 5 固定断言；2026-11-13 按用户要求改为跨缺席周连线）：
 * - 缺席周 null 原样透传（不造点不补值）、connectNulls:true 渲染层跨缺席周连线、smooth:false
 * - 单点（前后均无相邻非空点的孤立点）必须可见：showSymbol:true + symbolSize
 *   回调只给孤立点尺寸，非孤立点 0（300 只基金全显 symbol 会铺满画布）
 * - 纵轴 scale:true，不强制从零
 * - series 为全部命中基金，不按列表分页截断
 */

/** 一条曲线的输入（与后端 SharpeBoardSeriesDTO 对齐） */
export interface SharpeChartSeriesInput {
  code: string;
  name: string;
  values: (number | null)[];
}

export interface SharpeChartInput {
  /** 统一周历（周一日期，升序） */
  weeks: string[];
  series: SharpeChartSeriesInput[];
  /** 夏普下限参考线；null 不画线 */
  minLatestSharpe: number | null;
  /** 图例取消选中的 code 集（列表隐藏/聚焦联动）；缺省全部可见 */
  hiddenCodes?: ReadonlySet<string>;
}

/** 孤立点判定：所在连续非空段长度为 1 的点（单点可见的依据，可独立测试） */
export function isolatedPoints(values: (number | null)[]): boolean[] {
  const n = values.length;
  const out: boolean[] = new Array<boolean>(n).fill(false);
  let i = 0;
  while (i < n) {
    if (values[i] === null) {
      i += 1;
      continue;
    }
    let j = i;
    while (j < n && values[j] !== null) j += 1;
    if (j - i === 1) out[i] = true;
    i = j;
  }
  return out;
}

/** 调色板：300 只基金循环使用（避开涨跌红绿语义色） */
const PALETTE = [
  '#4e79a7', '#f28e2b', '#59a14f', '#b07aa1', '#76b7b2',
  '#e15759', '#edc948', '#9c755f', '#8cd17d', '#c9a0dc',
  '#86bcb6', '#d37295', '#a0cbe8', '#ffbe7d', '#79706e',
] as const;

interface SeriesSpec {
  name: string;
  type: 'line';
  data: (number | null)[];
  connectNulls: true;
  smooth: false;
  showSymbol: true;
  symbolSize: (value: unknown, params: { dataIndex: number }) => number;
  lineStyle: { width: number; color: string };
  itemStyle: { color: string };
  emphasis: { focus: 'series' };
  markLine?: Record<string, unknown>;
}

/** option 结构（宽松自定义类型，避免拉入 echarts 类型依赖；index signature 兼容 ECBasicOption） */
export interface SharpeChartOption {
  [key: string]: unknown;
  animation: false;
  color: string[];
  grid: { left: number; right: number; top: number; bottom: number };
  legend: {
    type: 'scroll';
    top: number;
    data: { name: string }[];
    selected: Record<string, boolean>;
    formatter: (name: string) => string;
  };
  tooltip: {
    trigger: 'axis';
    confine: true;
    order: 'valueDesc';
    formatter: (params: unknown) => string;
  };
  xAxis: {
    type: 'category';
    data: string[];
    boundaryGap: false;
    axisLabel: { color: string; fontSize: number; formatter: (value: string) => string };
  };
  yAxis: {
    type: 'value';
    scale: true;
    axisLabel: { color: string; fontSize: number; formatter: (value: number) => string };
    splitLine: { lineStyle: { color: string } };
  };
  dataZoom: Array<Record<string, unknown>>;
  series: SeriesSpec[];
}

/** 周一日期 → 稀疏轴标签（跨年显示年，同年月切显示 MM-DD） */
function weekLabel(value: string): string {
  const month = value.slice(5, 7);
  if (month === '01') return value.slice(0, 4);
  return value.slice(5, 10);
}

/**
 * 构造夏普曲线 option（纯函数；隐藏容器/实例生命周期由 SharpeChart.tsx 负责）
 *
 * - series.name 用 code（同名基金图例/选中状态互不干扰），展示名由 legend.formatter
 *   与 tooltip formatter 从 nameByCode 解析
 * - 下限参考线挂在第一条 series 的 markLine（无 series 时无线可挂，图区由调用方提示）
 */
export function buildSharpeChartOption(input: SharpeChartInput): SharpeChartOption {
  const { weeks, series, minLatestSharpe, hiddenCodes } = input;
  const hidden = hiddenCodes ?? new Set<string>();
  const nameByCode = new Map<string, string>(series.map(s => [s.code, s.name]));

  const seriesSpecs: SeriesSpec[] = series.map((s, idx) => {
    const iso = isolatedPoints(s.values);
    const color = PALETTE[idx % PALETTE.length];
    const spec: SeriesSpec = {
      name: s.code,
      type: 'line',
      data: s.values,
      connectNulls: true,
      smooth: false,
      showSymbol: true,
      symbolSize: (_value: unknown, params: { dataIndex: number }) =>
        iso[params.dataIndex] ? 4 : 0,
      lineStyle: { width: 1.5, color },
      itemStyle: { color },
      emphasis: { focus: 'series' },
    };
    return spec;
  });

  // 夏普下限参考线（含等于只是筛选语义；线只提示位置）
  if (minLatestSharpe !== null && seriesSpecs.length > 0) {
    seriesSpecs[0].markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { type: 'dashed', color: '#c56722', width: 1.2 },
      label: {
        show: true,
        position: 'insideEndTop',
        formatter: `下限 ${minLatestSharpe}`,
        fontSize: 11,
        color: '#c56722',
      },
      data: [{ yAxis: minLatestSharpe }],
    };
  }

  const legendSelected: Record<string, boolean> = {};
  for (const s of series) legendSelected[s.code] = !hidden.has(s.code);

  return {
    animation: false,
    color: [...PALETTE],
    grid: { left: 56, right: 20, top: 48, bottom: 64 },
    legend: {
      type: 'scroll',
      top: 8,
      data: series.map(s => ({ name: s.code })),
      selected: legendSelected,
      formatter: (code: string) => {
        const name = nameByCode.get(code);
        return name ? `${name} ${code}` : code;
      },
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      order: 'valueDesc',
      formatter: (params: unknown) => {
        const list = params as Array<{ seriesName?: string; value?: number | string | null }>;
        const week = (list[0] as { axisValue?: string } | undefined)?.axisValue ?? '';
        const hits = list.filter(p => typeof p.value === 'number');
        const shown = hits.slice(0, 10);
        const lines: string[] = [`<b>${week}</b>`];
        for (const p of shown) {
          const code = p.seriesName ?? '';
          const name = nameByCode.get(code) ?? '';
          lines.push(`${name}（${code}）　<b>${(p.value as number).toFixed(2)}</b>`);
        }
        if (hits.length > shown.length) lines.push(`…另有 ${hits.length - shown.length} 只`);
        if (hits.length === 0) lines.push('本周无在榜记录');
        return lines.join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      data: weeks,
      boundaryGap: false,
      axisLabel: { color: '#8c6847', fontSize: 11, formatter: weekLabel },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: {
        color: '#8c6847',
        fontSize: 11,
        formatter: (value: number) => value.toFixed(1),
      },
      splitLine: { lineStyle: { color: '#f0e6d4' } },
    },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      {
        type: 'slider',
        height: 18,
        bottom: 12,
        borderColor: '#eadcc9',
        fillerColor: 'rgba(197,103,34,0.14)',
        handleStyle: { color: '#c56722' },
        textStyle: { color: '#a5876a', fontSize: 10 },
        dataBackground: {
          lineStyle: { color: '#d7bea0' },
          areaStyle: { color: 'rgba(215,190,160,0.3)' },
        },
      },
    ],
    series: seriesSpecs,
  };
}
