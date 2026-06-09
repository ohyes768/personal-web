/**
 * react-plotly.js 模块声明 shim
 *
 * 原因：项目使用 @types/plotly.js 提供 plotly 类型。
 * 但 react-plotly.js 包本身不自带类型，TypeScript 找不到模块声明。
 *
 * 用 shim 把 react-plotly.js 声明为 any 类型，避免 @types/react-plotly.js
 * 引入的更严格类型与现有代码冲突。
 */
declare module 'react-plotly.js';
