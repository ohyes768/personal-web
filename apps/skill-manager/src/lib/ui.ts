/**
 * 目标管理两页（安装目标 / 导出目标）共享的控件语言常量。
 *
 * 2026-10 UI 统一评审的基准：以导出侧控件语言为准、冷色系
 * （slate/sky/rose/emerald/amber），不接平台暖白 token。
 * 危险色语义全 app 一致：rose 文字 = 卡内危险入口；rose-600 实心 =
 * 确认弹窗内的不可逆动作；sky 实心 = 普通确认。
 */
export const ghostButton =
  'rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50';
export const primaryButton =
  'rounded bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-700 disabled:opacity-50';
export const dialogGhostButton =
  'rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50';
export const dialogPrimaryButton =
  'rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700 disabled:opacity-50';
export const dialogDangerButton =
  'rounded bg-rose-600 px-4 py-2 text-sm text-white hover:bg-rose-700 disabled:opacity-50';
export const cardClass = 'rounded-lg border border-slate-200 bg-white p-4';
export const errorBlockClass = 'rounded bg-rose-50 p-3 text-sm text-rose-700';
export const emptyStateClass =
  'rounded-lg border border-dashed border-slate-300 p-8 text-center';
export const inputClass =
  'mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-sky-500 focus:outline-none';
