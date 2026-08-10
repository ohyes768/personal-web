/**
 * plotly.js 子路径类型声明 shim
 *
 * 原因:usePlotlyAutoResize.ts 动态 import 的是 'plotly.js/dist/plotly.js'(浏览器可用版本,
 * 已被 react-plotly.js 打入 bundle)。@types/plotly.js 只声明了主包 'plotly.js',
 * 不覆盖子路径,导致 strict 模式下报 "implicitly has an 'any' type"。
 *
 * 把子路径类型映射到主包,既保留类型检查又不破坏运行时的子路径 import。
 */
declare module 'plotly.js/dist/plotly.js' {
  import Plotly from 'plotly.js';
  export default Plotly;
}
