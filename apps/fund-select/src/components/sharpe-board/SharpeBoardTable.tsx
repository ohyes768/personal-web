/**
 * 夏普榜单分页列表（R3：代码、名称、累计在榜周数、最近上榜夏普、最近上榜周、
 * 是否在最新成功榜单内、最近一段连续周数）
 *
 * - 排序由后端完成（listed_weeks DESC, latest_sharpe DESC, code ASC），表格不排序
 * - 「聚焦」按钮联动总图：单看这只基金的曲线（再点取消）
 * - 数值列用 tnum；名称截断 + hover 原名（颜色之外的第二信息通道）
 */
'use client';

import Link from 'next/link';

import type { SharpeBoardItem } from '@/lib/sharpe-board';
import { formatWeekDay } from '@/lib/sharpe-board';
import { sharpeTrendHref } from '@/lib/sharpe-trend';

interface SharpeBoardTableProps {
  items: SharpeBoardItem[];
  loading: boolean;
  /** 当前聚焦的 code（高亮行）；null = 未聚焦 */
  focusCode: string | null;
  /** 点击行 / 聚焦按钮：切换聚焦 */
  onFocusToggle: (code: string) => void;
  /** 点击代码 / 名称：打开基金详情抽屉 */
  onOpenDetail: (code: string, name: string) => void;
}

const NAME_MAX = 12;

/** 收益（百分数）→ 带符号两位小数 + %；null → - */
function formatRet(v: number | null): string {
  if (v === null) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

/** 涨红跌绿（与站内 up/down 语义一致），null 不着色 */
function retClass(v: number | null): string {
  if (v === null) return 'text-ink-muted';
  return v >= 0 ? 'text-up' : 'text-down';
}

const th = 'px-1.5 py-2 text-left text-xs font-medium text-ink-muted';
const td = 'px-1.5 py-1.5 align-middle';

export function SharpeBoardTable({ items, loading, focusCode, onFocusToggle, onOpenDetail }: SharpeBoardTableProps) {
  if (loading) {
    return (
      <div className="p-8 space-y-2 animate-pulse" aria-label="加载中">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-9 bg-paper-tint rounded" />
        ))}
      </div>
    );
  }

  // 空态由页面级空态卡（SharpeBoardEmptyCard）呈现，不渲染空表头
  if (items.length === 0) return null;

  return (
    <div className="w-full min-w-0 overflow-x-auto">
      <table className="w-full min-w-[560px] table-fixed text-xs">
        <thead className="border-b border-rule-strong">
          <tr>
            <th className={`${th} w-[4.5rem]`}>代码</th>
            <th className={`${th} w-[8rem]`}>名称</th>
            <th className={`${th} text-right`}>近1年收益</th>
            <th className={`${th} text-right`}>近3年收益</th>
            <th className={`${th} text-right`}>累计在榜周数</th>
            <th className={`${th} text-right`}>最近连续周数</th>
            <th className={`${th} text-right`}>最近上榜夏普</th>
            <th className={`${th} text-right`}>最近上榜周</th>
            <th className={`${th} text-center`}>最新周榜</th>
            <th className={`${th} w-[3.5rem] text-center`}>图</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => {
            const focused = item.code === focusCode;
            return (
              <tr
                key={item.code}
                className={`border-b border-rule transition-colors hover:bg-paper-tint cursor-pointer ${
                  focused ? 'bg-info-tint' : ''
                }`}
                onClick={() => onFocusToggle(item.code)}
              >
                <td className={`${td} font-mono whitespace-nowrap`}>
                  {/* 代码 → 夏普走势页（完整滚动曲线）；详情抽屉仍由名称点击打开 */}
                  <Link
                    href={sharpeTrendHref(item.code)}
                    className="text-info underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-info"
                    aria-label={`查看 ${item.name} 夏普走势`}
                    title="查看夏普走势"
                    onClick={e => e.stopPropagation()}
                  >
                    {item.code}
                  </Link>
                  <button
                    type="button"
                    className="block text-[10px] text-ink-soft hover:text-info underline-offset-2 hover:underline"
                    aria-label={`查看 ${item.name} 详情`}
                    onClick={e => {
                      e.stopPropagation();
                      onOpenDetail(item.code, item.name);
                    }}
                  >
                    详情
                  </button>
                </td>
                <td className={`${td} text-ink-strong`}>
                  <button
                    type="button"
                    className="text-left underline-offset-4 hover:underline"
                    onClick={e => {
                      e.stopPropagation();
                      onOpenDetail(item.code, item.name);
                    }}
                  >
                    <span
                      className={item.name.length > NAME_MAX ? 'hover-tip' : undefined}
                      data-tip={item.name.length > NAME_MAX ? item.name : undefined}
                    >
                      {item.name.length > NAME_MAX ? `${item.name.slice(0, NAME_MAX)}…` : item.name}
                    </span>
                  </button>
                </td>
                <td className={`${td} text-right tnum whitespace-nowrap ${retClass(item.ret_1y)}`}>
                  {formatRet(item.ret_1y)}
                </td>
                <td className={`${td} text-right tnum whitespace-nowrap ${retClass(item.ret_3y)}`}>
                  {formatRet(item.ret_3y)}
                </td>
                <td className={`${td} text-right tnum font-semibold text-ink-strong`}>{item.listed_weeks}</td>
                <td className={`${td} text-right tnum text-ink-muted`}>{item.consecutive_weeks}</td>
                <td className={`${td} text-right tnum whitespace-nowrap`}>
                  {item.latest_sharpe !== null ? item.latest_sharpe.toFixed(2) : '-'}
                </td>
                <td className={`${td} text-right tnum whitespace-nowrap`}>
                  {item.last_listed_week !== null ? formatWeekDay(item.last_listed_week) : '-'}
                </td>
                <td className={`${td} text-center`}>
                  {item.on_latest_board ? (
                    <span className="text-up" aria-label="在最新成功榜单内">在榜</span>
                  ) : (
                    <span className="text-ink-soft" aria-label="不在最新成功榜单内">—</span>
                  )}
                </td>
                <td className={`${td} text-center`}>
                  <button
                    type="button"
                    aria-pressed={focused}
                    aria-label={focused ? `取消聚焦 ${item.name}` : `在图中聚焦 ${item.name}`}
                    className="px-1.5 py-0.5 rounded text-info underline-offset-4 hover:underline"
                    onClick={e => {
                      e.stopPropagation();
                      onFocusToggle(item.code);
                    }}
                  >
                    {focused ? '取消' : '聚焦'}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
