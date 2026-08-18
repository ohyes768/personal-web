'use client';

/**
 * 单张分组卡片
 * - 卡头第一行(小字标识):圆点 + 分组名 + 「X 项指标」
 * - 卡头第二行(档位刻度):全部档位横排,当前档大字+档位色突出,其余小字灰色;
 *   定位不到当前档时兜底显示 conclusion(白)或「数据缺失」(灰)大字
 * - 指标列表:每行 label + value + 三时间(数据/分析/下期预期)
 * - 整组 indicators 为空 → 列表区显示「本月数据缺失」占位
 */
import type { DimensionKey, MacroSignalGroup, MacroIndicator } from '@/lib/modules/macro-signal/types';
import type { TabType } from '@/lib/types/economic';
import { GROUP_META, GROUP_SCALES, findActiveLevel, getIndicatorMeta, INDICATOR_LINK_MAP } from './constants';

interface GroupCardProps {
  groupKey: DimensionKey;
  group: MacroSignalGroup;
  /** 所选月份 'YYYY-MM',用于判断指标数据是否偏旧 */
  selectedMonth: string;
  /** 指标跳转回调(若有该指标的曲线 Tab),由父级透传 */
  onJumpToTab?: (tab: TabType) => void;
}

/** 格式化指标数值 */
function formatValue(v: number | null | undefined, meta: { digits?: number; unit?: string }): string {
  if (v === null || v === undefined) return '—';
  const d = meta.digits ?? 2;
  const u = meta.unit ?? '';
  return Number(v).toFixed(d) + u;
}

/** ISO 日期 → 相对时间(基于数据时间);≥30 天用「N 个月前」,不回退原始日期(前面已展示,重复无信息量) */
function relativeDate(iso: string | null): string {
  if (!iso) return '无数据';
  const d = new Date(iso + 'T00:00:00Z');
  const now = new Date();
  const days = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (days <= 0) return '今日更新';
  if (days === 1) return '1 天前';
  if (days < 30) return `${days} 天前`;
  return `${Math.floor(days / 30)} 个月前`;
}

/** 分析时间 ISO timestamp → 本地 'MM-DD HH:mm'(转北京时间等本地时区) */
function formatAnalyzed(ts: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 判断指标是否偏旧(距所选月初 35 天以上) */
function isStale(updatedAt: string | null, selectedMonth: string): boolean {
  if (!updatedAt) return false;
  const monthStart = new Date(selectedMonth + '-01T00:00:00Z');
  const d = new Date(updatedAt + 'T00:00:00Z');
  return monthStart.getTime() - d.getTime() > 35 * 86400000;
}

/** 指标行:label + value + 三时间(数据/分析/下期预期) */
function IndicatorRow({
  ind,
  selectedMonth,
  onJumpToTab,
}: {
  ind: MacroIndicator;
  selectedMonth: string;
  onJumpToTab?: (tab: TabType) => void;
}) {
  const meta = getIndicatorMeta(ind.key);
  const hasValue = ind.value !== null && ind.value !== undefined;
  // 兼容期:data_date 优先,旧接口回退 updated_at
  const dataDate = ind.data_date ?? ind.updated_at ?? null;
  const stale = isStale(dataDate, selectedMonth);
  const linkTab = INDICATOR_LINK_MAP[ind.key];
  // 日频指标每个工作日都更新,「下次」无信息量 → 只有月频才渲染
  const isMonthly = ind.frequency !== 'daily';
  // 日频指标分层展示:历史月显示月均(整月代表性口径),当月显示最新日度值
  const isCurrentMonth =
    selectedMonth === `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`;
  const showMonthAvg = ind.frequency === 'daily' && !isCurrentMonth && ind.month_avg != null;
  // 月频数据时间只显到年月(日的精度无意义),相对时间也省略;悬停 title 保留完整日期
  const dataDateText = isMonthly && dataDate ? dataDate.slice(0, 7) : dataDate;
  // 「暂未获取」占位态:该月无数据(value 空)但可推预期发布日
  const isPlaceholder = !hasValue && !!ind.next_release_at;
  const nextReleaseShort = isMonthly && ind.next_release_at ? ind.next_release_at.slice(5) : null;
  const nextReleaseTitle = ind.next_release_at
    ? `下期预期 ${ind.next_release_at}${ind.next_release_note ? ` · ${ind.next_release_note}` : ''}`
    : undefined;

  return (
    <div className="flex items-baseline justify-between py-2 border-b border-gray-800 last:border-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-gray-300">{meta.label}</span>
          {linkTab && onJumpToTab && (
            <button
              type="button"
              onClick={() => onJumpToTab(linkTab)}
              title={`查看 ${meta.label} 曲线`}
              className="text-gray-500 hover:text-blue-400 transition-colors text-xs leading-none"
            >
              📈
            </button>
          )}
        </div>
        {/* 三时间行:数据时间(+相对时间) · 分析时间 · 下期预期 */}
        <div className={`text-xs mt-0.5 flex flex-wrap items-baseline gap-x-2 ${stale ? 'text-yellow-600' : 'text-gray-500'}`}>
          {dataDate ? (
            <span title={isMonthly ? `数据时间 ${dataDate}` : undefined}>
              数据 <span className="font-mono">{dataDateText}</span>
              {!isMonthly && (
                <>
                  {' · '}{relativeDate(dataDate)}
                </>
              )}
              {stale ? ' · 数据偏旧' : ''}
            </span>
          ) : isPlaceholder ? (
            <span title={nextReleaseTitle} className="cursor-help">
              暂未获取{nextReleaseShort ? <> · 预计 <span className="font-mono">≈{nextReleaseShort}</span> 发布</> : null}
            </span>
          ) : (
            <span>本月无数据</span>
          )}
          {ind.analyzed_at && (
            <span title={`分析时间 ${ind.analyzed_at}`}>
              分析 <span className="font-mono">{formatAnalyzed(ind.analyzed_at)}</span>
            </span>
          )}
          {/* 占位行「预计…发布」已含发布日,不再重复渲染「下次」段 */}
          {!isPlaceholder && nextReleaseShort && (
            <span title={nextReleaseTitle} className="cursor-help">
              下次 <span className="font-mono">≈{nextReleaseShort}</span>
            </span>
          )}{ind.frequency === 'daily' && !showMonthAvg && (
            <span title="日频指标,每个工作日更新">日频</span>
          )}{showMonthAvg && (
            <span title="日频指标,显示该月读数均值(数据截至所列日期)">月均</span>
          )}
        </div>
      </div>
      <div
        className={`text-lg font-mono ml-3 ${hasValue ? 'text-white' : 'text-gray-600'}`}
        title={showMonthAvg ? `该月均值(最新读数 ${formatValue(ind.value, meta)})` : undefined}
      >
        {showMonthAvg ? formatValue(ind.month_avg, meta) : formatValue(ind.value, meta)}
      </div>
    </div>
  );
}

export function GroupCard({ groupKey, group, selectedMonth, onJumpToTab }: GroupCardProps) {
  const meta = GROUP_META[groupKey];
  const indicators = group.indicators ?? [];
  const isEmpty = indicators.length === 0;
  // conclusion 为空时的兜底文案:组内有占位指标(可推预期发布)说明「暂未获取」,
  // 连占位都没有才是真「数据缺失」——与指标行口径一致
  const hasPlaceholder = indicators.some(i => i.value == null && i.next_release_at);
  const conclusionText = group.conclusion ?? (hasPlaceholder ? '暂未获取' : '数据缺失');
  // 当前档位:conclusion 文本匹配优先、total_score 区间兜底;刻度行内当前档大字染色突出
  const activeLevel = findActiveLevel(groupKey, group.conclusion, group.total_score);
  const scales = GROUP_SCALES[groupKey];

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 hover:border-gray-600 transition-colors">
      {/* 卡头 */}
      <div className="mb-4 pb-3 border-b border-gray-800">
        <div className="flex items-center gap-1.5 mb-2">
          <span className={`w-2 h-2 rounded-full ${meta.calendarColor}`}></span>
          <span className="text-xs text-gray-400">{meta.title}</span>
          <span className="ml-auto text-xs text-gray-500">{indicators.length} 项指标</span>
        </div>
        {/* 档位刻度:全部档位横排作参照系,当前档大字+档位色突出,其余小字灰色;定位不到当前档时兜底显示 conclusion 大字 */}
        {activeLevel && scales ? (
          <div className="flex flex-wrap items-baseline">
            {scales.map((lvl, i) => {
              const isActive = activeLevel.label === lvl.label;
              return (
                <span key={lvl.label} className="flex items-baseline whitespace-nowrap">
                  {i > 0 && <span className="text-gray-700 mx-1.5">·</span>}
                  <span
                    className={isActive ? `text-xl font-bold tracking-wide ${lvl.activeClass}` : 'text-xs text-gray-600'}
                    title={isActive ? `当前档位(总分区间 ${lvl.min}-${lvl.max})` : `总分区间 ${lvl.min}-${lvl.max}`}
                  >
                    {lvl.label}
                  </span>
                </span>
              );
            })}
          </div>
        ) : (
          <div className={`text-xl font-bold tracking-wide ${group.conclusion ? 'text-white' : 'text-gray-600'}`}>{conclusionText}</div>
        )}
      </div>

      {/* 指标列表 */}
      {isEmpty ? (
        <div className="text-sm text-gray-600 py-6 text-center">本月数据缺失</div>
      ) : (
        <div>
          {indicators.map(ind => (
            <IndicatorRow
              key={ind.key}
              ind={ind}
              selectedMonth={selectedMonth}
              onJumpToTab={onJumpToTab}
            />
          ))}
        </div>
      )}
    </div>
  );
}
