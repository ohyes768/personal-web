'use client';

/**
 * 对比模块 — 指标多选器
 * 按数据源分组渲染 checkbox，上限 6 条，localStorage 持久化
 */
import { useEffect, useState } from 'react';
import { INDICATORS, GROUP_ORDER, MAX_INDICATORS, DEFAULT_INDICATORS } from '@/lib/modules/comparison/indicators';
import type { IndicatorId } from '@/lib/modules/comparison/types';

const STORAGE_KEY = 'comparison_selected_indicators';

interface IndicatorSelectorProps {
  value: IndicatorId[];
  onChange: (next: IndicatorId[]) => void;
}

function loadFromStorage(): IndicatorId[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.every((id) => id in INDICATORS)) {
      return parsed.slice(0, MAX_INDICATORS) as IndicatorId[];
    }
  } catch {
    /* ignore */
  }
  return null;
}

function saveToStorage(ids: IndicatorId[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* ignore */
  }
}

export function IndicatorSelector({ value, onChange }: IndicatorSelectorProps) {
  // 首次挂载从 localStorage 恢复，否则用默认值
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    const stored = loadFromStorage();
    if (stored && stored.length > 0) {
      onChange(stored);
    } else if (value.length === 0) {
      onChange(DEFAULT_INDICATORS);
    }
    setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 选中状态变化时持久化
  useEffect(() => {
    if (hydrated) saveToStorage(value);
  }, [value, hydrated]);

  const toggle = (id: IndicatorId) => {
    if (value.includes(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      if (value.length >= MAX_INDICATORS) return;  // 上限保护
      onChange([...value, id]);
    }
  };

  return (
    <div className="bg-gray-900 rounded-lg p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-white">选择对比指标</h3>
        <span className="text-sm text-gray-400">
          已选 {value.length} / {MAX_INDICATORS}
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {GROUP_ORDER.map(({ group, label }) => {
          const items = (Object.values(INDICATORS) as Array<typeof INDICATORS[IndicatorId]>)
            .filter((m) => m.group === group);
          return (
            <div key={group}>
              <div className="text-sm font-medium text-gray-400 mb-2">{label}</div>
              <div className="space-y-1">
                {items.map((m) => {
                  const checked = value.includes(m.id);
                  const disabled = !checked && value.length >= MAX_INDICATORS;
                  return (
                    <label
                      key={m.id}
                      className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-colors ${
                        disabled
                          ? 'opacity-40 cursor-not-allowed'
                          : checked
                            ? 'bg-gray-800'
                            : 'hover:bg-gray-800/50'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={() => toggle(m.id)}
                        className="w-4 h-4 accent-blue-500"
                      />
                      <span
                        className="inline-block w-3 h-3 rounded-sm flex-shrink-0"
                        style={{ backgroundColor: m.color }}
                      />
                      <span className="text-sm text-gray-200 truncate">{m.label}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
