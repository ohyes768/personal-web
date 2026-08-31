'use client';

/**
 * 日频卡片网格(3 维度卡片)
 * - 卡头:色点 + 维度名 + 「N 项 · 截至 MM-DD」(无档位刻度:日频无 skill 评分)
 * - 指标行:label + 最新值 + 较前一交易日绝对变化(▲红 / ▼绿,A股习惯)
 *   回退(data_date ≠ 所选日期)时 label 下灰字标注实际日期
 */
import type { DailyIndicator, DailySnapshot } from '@/lib/modules/macro-signal/types';
import type { TabType } from '@/lib/types/economic';
import { GROUP_META, DAILY_GROUPS, getIndicatorMeta, INDICATOR_LINK_MAP } from './constants';

interface DailyCardGridProps {
  snapshot: DailySnapshot;
  /** 指标跳转回调(若有该指标的曲线 Tab),由父级透传 */
  onJumpToTab?: (tab: TabType) => void;
}

/** 日变化文本:▲/▼ + 与值同小数位的绝对变化;无变化或无前值显示 — */
function changeText(change: number, digits: number): { text: string; className: string } {
  if (change === 0) return { text: '—', className: 'text-gray-500' };
  const sign = change > 0 ? '▲' : '▼';
  // A股习惯:红涨绿跌
  const className = change > 0 ? 'text-red-400' : 'text-emerald-400';
  return { text: `${sign}${Math.abs(change).toFixed(digits)}`, className };
}

/** 单个指标行 */
function DailyIndicatorRow({
  ind,
  selectedDate,
  onJumpToTab,
}: {
  ind: DailyIndicator;
  selectedDate: string;
  onJumpToTab?: (tab: TabType) => void;
}) {
  const meta = getIndicatorMeta(ind.key);
  const digits = meta.digits ?? 2;
  const hasValue = ind.value !== null && ind.value !== undefined;
  const change = hasValue && ind.prev_value !== null && ind.prev_value !== undefined
    ? ind.value! - ind.prev_value
    : null;
  const chg = change !== null ? changeText(change, digits) : null;
  // 回退:接口按 asof 给了最近可得值,实际数据日期 ≠ 所选日期 → 行内标注
  const isFallback = ind.data_date !== null && ind.data_date !== selectedDate;
  const linkTab = INDICATOR_LINK_MAP[ind.key];
  const canJump = !!(linkTab && onJumpToTab);
  const rowClass = [
    'flex w-full items-baseline justify-between py-1 border-b border-gray-800 last:border-0 text-left',
    canJump ? 'group rounded-md -mx-1 px-1 cursor-pointer hover:bg-gray-800/80' : '',
  ].join(' ');

  const body = (
    <>
      <div className="flex items-center gap-1.5 min-w-0">
        <span className={`text-sm truncate ${canJump ? 'text-gray-300 group-hover:text-white' : 'text-gray-300'}`}>
          {meta.label}
        </span>
        {canJump && (
          <span className="text-gray-500 group-hover:text-blue-400 transition-colors text-xs leading-none shrink-0" aria-hidden>
            📈
          </span>
        )}
        {isFallback && (
          <span className="text-[10px] text-gray-500 font-mono shrink-0" title="所查日期无更新,已回退最近可得值">
            {ind.data_date?.slice(5)}
          </span>
        )}
      </div>
      <div className="flex items-baseline gap-2 ml-3 shrink-0">
        <span className={`text-base font-mono ${hasValue ? 'text-white' : 'text-gray-600'}`}>
          {hasValue ? ind.value!.toFixed(digits) + (meta.unit ?? '') : '—'}
        </span>
        {chg && <span className={`text-xs font-mono ${chg.className}`}>{chg.text}</span>}
      </div>
    </>
  );

  if (canJump) {
    return (
      <button
        type="button"
        onClick={() => onJumpToTab!(linkTab)}
        title={`查看 ${meta.label} 曲线`}
        className={`${rowClass} bg-transparent border-0`}
      >
        {body}
      </button>
    );
  }

  return <div className={rowClass}>{body}</div>;
}

export function DailyCardGrid({ snapshot, onJumpToTab }: DailyCardGridProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {DAILY_GROUPS.map(({ key, indicators: order }) => {
        const meta = GROUP_META[key];
        const group = snapshot.groups[key];
        const indicators = group?.indicators ?? [];
        // 按常量声明顺序渲染(后端返回顺序一致,此处显式排序防漂移)
        const byKey = new Map(indicators.map(i => [i.key, i]));
        const ordered = order.map(k => byKey.get(k)).filter(i => i !== undefined);
        // 卡头「截至」= 组内指标 data_date 的最大值
        const asOf = indicators.reduce<string | null>(
          (acc, i) => (i.data_date && (!acc || i.data_date > acc) ? i.data_date : acc),
          null,
        );

        return (
          <div key={key} className="bg-gray-900 border border-gray-800 rounded-lg p-3 hover:border-gray-600 transition-colors">
            {/* 卡头 */}
            <div className="mb-2 pb-2 border-b border-gray-800">
              <div className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${meta.calendarColor}`}></span>
                <span className="text-xs text-gray-400">{meta.title}</span>
                <span className="ml-auto text-xs text-gray-500">
                  {ordered.length} 项{asOf ? ` · 截至 ${asOf.slice(5)}` : ''}
                </span>
              </div>
            </div>

            {/* 指标列表 */}
            {ordered.length === 0 ? (
              <div className="text-sm text-gray-600 py-3 text-center">无数据</div>
            ) : (
              ordered.map(ind => (
                <DailyIndicatorRow
                  key={ind.key}
                  ind={ind}
                  selectedDate={snapshot.date}
                  onJumpToTab={onJumpToTab}
                />
              ))
            )}
          </div>
        );
      })}
    </div>
  );
}
