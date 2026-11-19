/**
 * AlertSettingsModal — 挡位监控设置弹框
 *
 * 4 档价格（重仓/加仓/减仓/全卖），每档含 price + 选填 pe
 * 元数据：updated_at（自动记录，只读显示）；推送与监控已移除，不再有启用开关
 *
 * 触发判断只在后端做（看价格），PE 仅作推送时展示。
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal } from './shared-ui/Modal';
import { Button } from './shared-ui/Button';
import type {
  AlertConfigRequest,
  AlertLevels,
  AlertLevel,
  DividendStock,
  TechnicalIndicators,
} from '@/lib/types';
import { formatBeijingTs } from '@/lib/formatTs';
import {
  correctLevelsByPrice,
  hasAllFourLevels,
  resolveValuationZone,
  VALUATION_ZONE_TEXT_COLOR,
  VALUATION_ZONE_LABEL,
  type ValuationZone,
} from '@/lib/valuation';

export interface AlertSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  stock: DividendStock | null;
  technical?: TechnicalIndicators | null;
  /** 该股票当前 alerts 配置（来自 useAlertsStatus.alertMap） */
  currentConfig?: AlertConfigRequest | null;
  /** 挡位最后更新时间（来自 currentConfig 被读时 item.updated_at） */
  currentUpdatedAt?: string | null;
  /** 保存回调（调用 useAlertsStatus.setAlerts） */
  onSubmit: (code: string, body: AlertConfigRequest) => Promise<void>;
  /** 清除回调（调用 useAlertsStatus.clearAlerts） */
  onClear: (code: string) => Promise<void>;
}

type LevelKey = 'heavy_position' | 'add_position' | 'reduce_position' | 'full_exit';

const LEVEL_DEFS: Array<{ key: LevelKey; label: string; emoji: string; hint: string }> = [
  { key: 'heavy_position',  label: '重仓档', emoji: '🟢', hint: '跌破此价 → 重仓买入（四档最低）' },
  { key: 'add_position',    label: '加仓档', emoji: '🟡', hint: '跌破此价 → 开始加仓' },
  { key: 'reduce_position', label: '减仓档', emoji: '🟠', hint: '涨破此价 → 开始减仓' },
  { key: 'full_exit',       label: '全卖档', emoji: '🔴', hint: '涨破此价 → 全部清仓（四档最高）' },
];

// 「当前所在区」标记落到哪一档行：五区里持有区无动作，不点亮任何行（最多亮一个，互斥）。
const ZONE_ROW: Record<ValuationZone, LevelKey | null> = {
  heavy: 'heavy_position',
  add: 'add_position',
  hold: null,
  reduce: 'reduce_position',
  full: 'full_exit',
};

const EMPTY_LEVELS: AlertLevels = {
  heavy_position: null,
  add_position: null,
  reduce_position: null,
  full_exit: null,
};

function levelsToForm(levels?: AlertLevels | null): AlertLevels {
  if (!levels) return { ...EMPTY_LEVELS };
  return {
    heavy_position:  levels.heavy_position  ? { price: levels.heavy_position.price,  pe: levels.heavy_position.pe  ?? null } : null,
    add_position:    levels.add_position    ? { price: levels.add_position.price,    pe: levels.add_position.pe    ?? null } : null,
    reduce_position: levels.reduce_position ? { price: levels.reduce_position.price, pe: levels.reduce_position.pe ?? null } : null,
    full_exit:       levels.full_exit       ? { price: levels.full_exit.price,       pe: levels.full_exit.pe       ?? null } : null,
  };
}

/** 右上角「更新于」文案：有挡位但时间缺失（老数据）时不能再说「从未设置」，否则与列表里的挡位条互相矛盾 */
function formatUpdatedAt(iso: string | null | undefined, hasLevels: boolean): string {
  if (!iso) return hasLevels ? '已设置' : '从未设置';
  return formatBeijingTs(iso) ?? iso;
}

export function AlertSettingsModal({
  isOpen,
  onClose,
  stock,
  technical,
  currentConfig,
  currentUpdatedAt,
  onSubmit,
  onClear,
}: AlertSettingsModalProps) {
  const [levels, setLevels] = useState<AlertLevels>({ ...EMPTY_LEVELS });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 挡位顺序异常：阻断保存（不猜、不放行），四档全填时提供按价格升序的自动纠正；
  // confirmClear：清除配置前的二次确认（替代原生 confirm()）
  const [orderWarnMsg, setOrderWarnMsg] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  // 同步 currentConfig 到本地表单：仅在打开、或服务器配置内容真正变化时。
  // currentConfig 是父组件每次渲染新建的对象（页面有 2s 级轮询重渲染），
  // 直接依赖对象引用会把用户正在编辑的值和警告面板每几秒冲掉一次。
  const configSig = useMemo(() => JSON.stringify(currentConfig?.levels ?? null), [currentConfig]);
  const lastSigRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isOpen) {
      lastSigRef.current = null;
      return;
    }
    if (lastSigRef.current === configSig) return; // 内容没变，只是引用变了
    lastSigRef.current = configSig;
    setLevels(levelsToForm(currentConfig?.levels));
    setError(null);
    setOrderWarnMsg(null);
    setConfirmClear(false);
  }, [isOpen, configSig, currentConfig]);

  const currentPrice = technical?.realtime ?? technical?.close ?? null;

  // 「当前所在区」单一标记：与收藏跟踪「区间」列同一口径（resolveValuationZone）。
  // 最多亮一个——现价落在哪一区，就在那一档点亮；持有区（无动作）不亮。
  // 四档未填齐时判不出区间，不亮（与价格条「不足两条线不画」的口径一致）。
  const zoneResult = useMemo(
    () => resolveValuationZone(levels, currentPrice ?? undefined),
    [levels, currentPrice],
  );
  const markerKey = zoneResult.zone ? ZONE_ROW[zoneResult.zone] : null;

  const updateLevel = (key: LevelKey, field: 'price' | 'pe' | 'pb', raw: string) => {
    setLevels(prev => {
      const next = { ...prev };
      const existing = prev[key] || { price: 0 };
      if (field === 'price') {
        const num = raw === '' ? 0 : parseFloat(raw);
        next[key] = { ...existing, price: isNaN(num) ? 0 : num };
      } else {
        // pe / pb 共享 same logic
        if (raw === '') {
          next[key] = { ...existing, [field]: null };
        } else {
          const num = parseFloat(raw);
          next[key] = { ...existing, [field]: isNaN(num) ? null : num };
        }
      }
      return next;
    });
  };

  const validLevels = useMemo(() => {
    // 价格 > 0 才算有效档位
    return (Object.keys(levels) as LevelKey[]).reduce<AlertLevels>((acc, key) => {
      const lv = levels[key];
      if (lv && lv.price > 0) {
        acc[key] = { price: lv.price, pe: lv.pe ?? null, pb: lv.pb ?? null };
      } else {
        acc[key] = null;
      }
      return acc;
    }, { ...EMPTY_LEVELS });
  }, [levels]);

  const validLevelCount = (Object.keys(validLevels) as LevelKey[]).filter(k => validLevels[k] !== null).length;

  const doSave = async () => {
    if (!stock) return;
    setSaving(true);
    try {
      const body: AlertConfigRequest = {
        levels: validLevels,
      };
      await onSubmit(stock.code, body);
      onClose();
    } catch (err) {
      // 统一「保存失败：」前缀（与全站错误态范式一致，不裸拼接口消息）
      setError(`保存失败：${err instanceof Error ? err.message : '请重试'}`);
    } finally {
      setSaving(false);
    }
  };

  const handleSave = async () => {
    if (!stock) return;
    setError(null);
    setOrderWarnMsg(null);

    if (validLevelCount === 0) {
      setError('至少需要配置 1 档价格');
      return;
    }

    // 校验：减仓 > 加仓，全卖 > 减仓，加仓 > 重仓（提示但不阻止 → 行内确认）
    const orderWarn = checkLevelOrder(validLevels);
    if (orderWarn) {
      setOrderWarnMsg(orderWarn);
      return;
    }

    await doSave();
  };

  const handleClearClick = () => {
    if (!stock) return;
    if (!confirmClear) {
      setConfirmClear(true);
      return;
    }
    setConfirmClear(false);
    setSaving(true);
    onClear(stock.code)
      .then(() => onClose())
      .catch(err => {
        setError(`清除失败：${err instanceof Error ? err.message : '请重试'}`);
      })
      .finally(() => setSaving(false));
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={stock ? `挡位设置 · ${stock.name} (${stock.code})` : '挡位设置'} size="md">
      <div className="space-y-4">
        {/* 当前价参考 */}
        <div className="flex items-center gap-3 px-3 py-2 bg-paper-tint rounded text-sm">
          <span className="text-ink-muted">当前价：</span>
          <span className="font-mono font-semibold text-ink">
            {currentPrice !== null ? `¥${currentPrice.toFixed(2)}` : '-'}
          </span>
          {technical?.m120 && (
            <span className="text-ink-muted">
              · M120: <span className="font-mono">{technical.m120.toFixed(2)}</span>
            </span>
          )}
          <span className="text-ink-muted ml-auto">
            更新于 <span className="font-mono text-ink">{formatUpdatedAt(currentUpdatedAt, validLevelCount > 0)}</span>
          </span>
        </div>

        {/* 4 档价格表 */}
        <div className="border border-rule rounded overflow-hidden">
          <div className="grid grid-cols-[100px_1fr_1fr_1fr_28px] gap-2 px-3 py-2 bg-paper-deep text-[11px] font-semibold text-ink-strong uppercase tracking-wider">
            <div>档位</div>
            <div className="text-right">价格（元）</div>
            <div className="text-right">PE（选填）</div>
            <div className="text-right">PB（选填）</div>
            <div></div>
          </div>
          {LEVEL_DEFS.map(({ key, label, emoji, hint }) => {
            const lv = levels[key];
            const priceStr = lv && lv.price ? String(lv.price) : '';
            const peStr = lv && lv.pe !== null && lv.pe !== undefined ? String(lv.pe) : '';
            const pbStr = lv && lv.pb !== null && lv.pb !== undefined ? String(lv.pb) : '';
            return (
              <div key={key} className="grid grid-cols-[100px_1fr_1fr_1fr_28px] gap-2 px-3 py-2 items-center border-t border-rule">
                <div className="flex flex-col">
                  <span className="text-sm text-ink">{emoji} {label}</span>
                  <span className="text-xs text-ink-muted">{hint}</span>
                </div>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  aria-label={`${label} 价格`}
                  value={priceStr}
                  onChange={e => updateLevel(key, 'price', e.target.value)}
                  className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm focus:outline-none focus:border-accent"
                />
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  placeholder="-"
                  aria-label={`${label} PE（选填）`}
                  value={peStr}
                  onChange={e => updateLevel(key, 'pe', e.target.value)}
                  className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm focus:outline-none focus:border-accent"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="-"
                  aria-label={`${label} PB（选填）`}
                  value={pbStr}
                  onChange={e => updateLevel(key, 'pb', e.target.value)}
                  className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm focus:outline-none focus:border-accent"
                />
                <div className="text-center">
                  {markerKey === key && zoneResult.zone && currentPrice !== null ? (
                    <span
                      title={`现价 ¥${currentPrice.toFixed(2)} 处于${VALUATION_ZONE_LABEL[zoneResult.zone]}`}
                      className="text-xs font-bold"
                      style={{ color: VALUATION_ZONE_TEXT_COLOR[zoneResult.zone] }}
                    >
                      ●
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>

        {orderWarnMsg && (
          <div className="border border-rule-strong bg-warn-tint rounded px-3 py-2 text-sm text-warn-deep" role="alert">
            <div className="font-medium">挡位价格顺序异常，已阻止保存：</div>
            <ul className="mt-1 list-disc list-inside text-ink">
              {orderWarnMsg.split('\n').map(line => (
                <li key={line}>{line.replace(/^· /, '')}</li>
              ))}
            </ul>
            {hasAllFourLevels(validLevels) && (
              <p className="mt-2 text-ink">
                四条线都填了但买线高于卖线，监控方向会反。可以按价格升序自动纠正（最低→重仓、次低→加仓、次高→减仓、最高→全卖），纠正后请再点保存。
              </p>
            )}
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setOrderWarnMsg(null)}>
                返回修改
              </Button>
              {hasAllFourLevels(validLevels) && (
                <Button size="sm" variant="primary" disabled={saving} onClick={() => {
                  setLevels(correctLevelsByPrice(validLevels));
                  setOrderWarnMsg(null);
                }}>
                  按价格自动纠正
                </Button>
              )}
            </div>
          </div>
        )}

        {error && (
          <div className="bg-down-tint border border-down text-down px-3 py-2 rounded text-sm">
            {error}
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex items-center justify-between pt-2">
          <div>
            <Button
              variant="ghost"
              onClick={handleClearClick}
              disabled={saving || !currentConfig}
              className={confirmClear ? 'text-down font-semibold' : 'text-down'}
            >
              {confirmClear ? '再点一次确认清除' : '清除挡位'}
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose} disabled={saving}>
              取消
            </Button>
            <Button variant="primary" onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '保存'}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/**
 * 检查挡位语义：买线（重仓/加仓）必须全低于卖线（减仓/全卖），
 * 组内 重仓<加仓、减仓<全卖。只查相邻对会漏掉「重仓 42 / 全卖 30」这类
 * 全反置（神华存量数据），所以买×卖每个交叉对都要查。
 * 返回警告字符串（不满足时）；返回空串表示 OK。
 */
function checkLevelOrder(levels: AlertLevels): string {
  const warnings: string[] = [];
  const label: Record<LevelKey, string> = {
    heavy_position: '重仓', add_position: '加仓', reduce_position: '减仓', full_exit: '全卖',
  };
  const price = (k: LevelKey) => levels[k]?.price ?? 0;
  const has = (k: LevelKey) => price(k) > 0;

  for (const b of ['heavy_position', 'add_position'] as const) {
    for (const s of ['reduce_position', 'full_exit'] as const) {
      if (has(b) && has(s) && price(b) >= price(s)) {
        warnings.push(`· ${label[b]}价（${price(b)}）应低于${label[s]}价（${price(s)}）`);
      }
    }
  }
  if (has('heavy_position') && has('add_position') && price('heavy_position') >= price('add_position')) {
    warnings.push(`· 重仓价应低于加仓价（${price('heavy_position')} ≥ ${price('add_position')}）`);
  }
  if (has('reduce_position') && has('full_exit') && price('reduce_position') >= price('full_exit')) {
    warnings.push(`· 减仓价应低于全卖价（${price('reduce_position')} ≥ ${price('full_exit')}）`);
  }
  return warnings.join('\n');
}
