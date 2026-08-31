'use client';

/**
 * 单张分组卡片
 * - 卡头第一行(小字标识):圆点 + 分组名 + 「X 项指标」
 * - 卡头第二行(档位刻度):全部档位横排,当前档大字+档位色突出,其余小字灰色;
 *   定位不到当前档时兜底显示 conclusion(白)或「数据缺失」(灰)大字
 * - 指标列表:每行名称+数值;数据/分析/下次在 title
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

/** 指标行悬停说明:数据/分析/下次等次要信息不占高度 */
function buildMonthlyRowTitle(opts: {
  label: string;
  canJump: boolean;
  isPlaceholder: boolean;
  dataDate: string | null;
  dataDateText: string | null;
  isMonthly: boolean;
  stale: boolean;
  analyzedAt: string | null;
  nextReleaseTitle?: string;
  showMonthAvg: boolean;
  latestValueText: string;
}): string {
  const parts: string[] = [];
  if (opts.canJump) parts.push(`查看 ${opts.label} 曲线`);
  if (opts.isPlaceholder) {
    parts.push(opts.nextReleaseTitle ?? '暂未获取');
  } else if (!opts.dataDate) {
    parts.push('本月无数据');
  } else {
    parts.push(`数据 ${opts.dataDateText ?? opts.dataDate}`);
    if (!opts.isMonthly) parts.push(relativeDate(opts.dataDate));
    if (opts.stale) parts.push('数据偏旧');
  }
  if (opts.analyzedAt) parts.push(`分析 ${formatAnalyzed(opts.analyzedAt)}`);
  if (!opts.isPlaceholder && opts.nextReleaseTitle) parts.push(opts.nextReleaseTitle);
  if (opts.showMonthAvg) parts.push(`月均（最新 ${opts.latestValueText}）`);
  return parts.join(' · ');
}

/** 指标行:一行名称+数值;次要时间在 title */
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
  const canJump = !!(linkTab && onJumpToTab);
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
  const nextReleaseTitle = isMonthly && ind.next_release_at
    ? `下期预期 ${ind.next_release_at}${ind.next_release_note ? ` · ${ind.next_release_note}` : ''}`
    : undefined;

  const rowTitle = buildMonthlyRowTitle({
    label: meta.label,
    canJump,
    isPlaceholder,
    dataDate,
    dataDateText,
    isMonthly,
    stale,
    analyzedAt: ind.analyzed_at ?? null,
    nextReleaseTitle,
    showMonthAvg,
    latestValueText: formatValue(ind.value, meta),
  });

  const rowClass = [
    'flex w-full items-baseline justify-between py-1 border-b border-gray-800 last:border-0 text-left',
    canJump ? 'group rounded-md -mx-1 px-1 cursor-pointer hover:bg-gray-800/80' : '',
  ].join(' ');

  const nameClass = stale
    ? 'text-yellow-500'
    : canJump
      ? 'text-gray-300 group-hover:text-white'
      : 'text-gray-300';

  const body = (
    <>
      <div className="flex items-center gap-1.5 min-w-0">
        <span className={`text-sm truncate ${nameClass}`}>{meta.label}</span>
        {canJump && (
          <span className="text-gray-500 group-hover:text-blue-400 transition-colors text-xs leading-none shrink-0" aria-hidden>
            📈
          </span>
        )}
        {showMonthAvg && <span className="text-[10px] text-gray-500 shrink-0">月均</span>}
      </div>
      <span className={`text-base font-mono ml-3 shrink-0 ${hasValue ? 'text-white' : 'text-gray-600'}`}>
        {showMonthAvg ? formatValue(ind.month_avg, meta) : formatValue(ind.value, meta)}
      </span>
    </>
  );

  if (canJump) {
    return (
      <button
        type="button"
        onClick={() => onJumpToTab!(linkTab)}
        title={rowTitle}
        className={`${rowClass} bg-transparent border-0`}
      >
        {body}
      </button>
    );
  }

  return (
    <div className={rowClass} title={rowTitle}>
      {body}
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
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-3 hover:border-gray-600 transition-colors">
      {/* 卡头 */}
      <div className="mb-2 pb-2 border-b border-gray-800">
        <div className="flex items-center gap-1.5 mb-1">
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
                    className={isActive ? `text-lg font-bold tracking-wide ${lvl.activeClass}` : 'text-xs text-gray-600'}
                    title={isActive ? `当前档位(总分区间 ${lvl.min}-${lvl.max})` : `总分区间 ${lvl.min}-${lvl.max}`}
                  >
                    {lvl.label}
                  </span>
                </span>
              );
            })}
          </div>
        ) : (
          <div className={`text-lg font-bold tracking-wide ${group.conclusion ? 'text-white' : 'text-gray-600'}`}>{conclusionText}</div>
        )}
      </div>

      {/* 指标列表 */}
      {isEmpty ? (
        <div className="text-sm text-gray-600 py-3 text-center">本月数据缺失</div>
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
