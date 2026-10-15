/**
 * skill-manager 全 app 共享的控件语言常量。
 *
 * 2026-10 UI 统一评审的基准：以导出侧控件语言为准、冷色系
 * （slate/sky/rose/emerald/amber），不接平台暖白 token。
 * 危险色语义全 app 一致：rose 文字 = 卡内危险入口；rose-600 实心 =
 * 确认弹窗内的不可逆动作；sky 实心 = 普通确认；slate 实心 = 新建/启动流程。
 *
 * 对比度（AA）：主按钮底色用 sky-700（白字 ~5.1:1；sky-600 白字仅 4.0:1 不达标，
 * 2026-10-15 页面级检测证实）；辅助文字一律 text-slate-500（4.76:1），
 * 禁用 text-slate-400（2.9:1）。
 */
export const ghostButton =
  'rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50';
export const ghostDangerButton =
  'rounded border border-slate-300 px-3 py-1.5 text-sm text-rose-700 hover:bg-rose-50 disabled:opacity-50';
export const primaryButton =
  'rounded bg-sky-700 px-3 py-1.5 text-sm text-white hover:bg-sky-800 disabled:opacity-50';
export const solidSecondaryButton =
  'rounded bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-800 disabled:opacity-50';
export const dialogGhostButton =
  'rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50';
export const dialogPrimaryButton =
  'rounded bg-sky-700 px-4 py-2 text-sm text-white hover:bg-sky-800 disabled:opacity-50';
export const dialogDangerButton =
  'rounded bg-rose-600 px-4 py-2 text-sm text-white hover:bg-rose-700 disabled:opacity-50';
export const cardClass = 'rounded-lg border border-slate-200 bg-white p-4';
export const errorBlockClass = 'rounded bg-rose-50 p-3 text-sm text-rose-700';
export const okBlockClass = 'rounded bg-emerald-50 p-3 text-sm text-emerald-700';
export const emptyStateClass =
  'rounded-lg border border-dashed border-slate-300 p-8 text-center';
export const inputClass =
  'mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm placeholder:text-slate-500 focus:border-sky-500 focus:outline-none';
/** 顶栏导航 tab（data-active 驱动选中态）。 */
export const navTabClass =
  'border-b-2 border-transparent px-3 pb-2 pt-2.5 text-sm text-slate-600 hover:text-slate-800 data-[active=true]:border-sky-600 data-[active=true]:font-medium data-[active=true]:text-slate-800';
/** 来源切换 segmented 按钮（容器需 rounded-md border bg-slate-50 p-0.5）。 */
export const segButtonClass =
  'rounded px-3 py-1.5 text-sm text-slate-500 transition-colors hover:text-slate-700 data-[active=true]:bg-white data-[active=true]:font-medium data-[active=true]:text-slate-800 data-[active=true]:shadow-sm';
/** 工具栏紧凑输入框/下拉（筛选条、看板搜索，区别于表单 inputClass）。 */
export const toolbarInput =
  'rounded border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-700 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none';
export const toolbarSelect =
  'rounded border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-700 focus:border-sky-500 focus:outline-none';
