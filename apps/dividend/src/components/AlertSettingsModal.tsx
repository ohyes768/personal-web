/**
 * AlertSettingsModal — 挡位监控设置弹框
 *
 * 4 档价格（重仓/加仓/减仓/全卖），每档含 price + 选填 pe
 * 元数据：enabled + updated_at（自动记录，只读显示）
 *
 * 触发判断只在后端做（看价格），PE 仅作推送时展示。
 */
'use client';

import { useEffect, useMemo, useState } from 'react';
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
  { key: 'heavy_position',  label: '重仓档', emoji: '🟢', hint: '买入最深，价格最低' },
  { key: 'add_position',    label: '加仓档', emoji: '🟡', hint: '开始加仓' },
  { key: 'reduce_position', label: '减仓档', emoji: '🟠', hint: '开始减仓' },
  { key: 'full_exit',       label: '全卖档', emoji: '🔴', hint: '全部清仓，价格最高' },
];

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

function formatUpdatedAt(iso?: string | null): string {
  if (!iso) return '从未设置';
  return formatBeijingTs(iso) ?? iso;
}

// 对接文档（外部 agent 调用 batch 接口的说明，常量避免每次渲染重建）
const AGENT_DOC_TEXT = `POST /api/dividend/favorites/alerts/batch
Header:
  Content-Type: application/json
  X-API-Token: <AGENT_API_TOKEN>    # 找运维拿，缺/错 → 401

请求体（一次最多 100 条）：
{
  "updates": [
    {
      "code": "600000",                      # 6 位股票代码
      "levels": {
        "heavy_position":  {"price": 10.0, "pe": 8.5, "pb": 1.2},  # 重仓（必填 price>0，pe/pb 选填）
        "add_position":    {"price": 12.0},                         # 加仓
        "reduce_position": {"price": 15.0},                         # 减仓
        "full_exit":       {"price": 18.0}                          # 全卖
      },
      "enabled": true                       # 选填，默认 true
    }
  ]
}

响应（HTTP 200，部分失败也是 200）：
{
  "results": [
    {"code": "600000", "ok": true, "error": null},
    {"code": "abc",    "ok": false, "error": "股票代码格式错误: abc"},
    {"code": "000001", "ok": false, "error": "000001 不在收藏中"}
  ],
  "success_count": 1,
  "fail_count": 2
}

说明：
- 4 档 price 必填 > 0；pe/pb/enabled 选填
- code 必须已收藏（POST /api/dividend/favorites/{code}）；未收藏 → 该条 fail，不会自动加入
- 每条独立处理，部分失败不影响其他
- 缺/错 token → 401；服务端未配 AGENT_API_TOKEN → 503`;

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
  const [enabled, setEnabled] = useState(false);
  const [levels, setLevels] = useState<AlertLevels>({ ...EMPTY_LEVELS });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopyDoc = async () => {
    try {
      await navigator.clipboard.writeText(AGENT_DOC_TEXT);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API 在非 HTTPS / 旧浏览器可能失败，静默忽略
    }
  };

  // 同步 currentConfig 到本地表单
  useEffect(() => {
    if (!isOpen) return;
    setEnabled(currentConfig?.enabled ?? false);
    setLevels(levelsToForm(currentConfig?.levels));
    setError(null);
  }, [isOpen, currentConfig]);

  const currentPrice = technical?.realtime ?? technical?.close ?? null;

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

  const handleSave = async () => {
    if (!stock) return;
    setError(null);

    if (enabled && validLevelCount === 0) {
      setError('启用监控时至少需要配置 1 档价格');
      return;
    }

    // 校验：减仓 > 加仓，全卖 > 减仓，加仓 > 重仓（提示但不阻止）
    const orderWarn = checkLevelOrder(validLevels);
    if (orderWarn) {
      const ok = confirm(`挡位价格顺序异常：\n${orderWarn}\n\n仍要保存？`);
      if (!ok) return;
    }

    setSaving(true);
    try {
      const body: AlertConfigRequest = {
        enabled,
        levels: validLevels,
      };
      await onSubmit(stock.code, body);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!stock) return;
    const ok = confirm(`确认清除 ${stock.name}（${stock.code}）的挡位配置？`);
    if (!ok) return;
    setSaving(true);
    try {
      await onClear(stock.code);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '清除失败';
      setError(msg);
    } finally {
      setSaving(false);
    }
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
            更新于 <span className="font-mono text-ink">{formatUpdatedAt(currentUpdatedAt)}</span>
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
            const hit = currentPrice !== null && lv && lv.price > 0
              ? (key === 'heavy_position' || key === 'add_position'
                  ? currentPrice <= lv.price
                  : currentPrice >= lv.price)
              : false;
            return (
              <div key={key} className="grid grid-cols-[100px_1fr_1fr_1fr_28px] gap-2 px-3 py-2 items-center border-t border-rule">
                <div className="flex flex-col">
                  <span className="text-sm text-ink">{emoji} {label}</span>
                  <span className="text-[10px] text-ink-muted">{hint}</span>
                </div>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  value={priceStr}
                  onChange={e => updateLevel(key, 'price', e.target.value)}
                  className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm focus:outline-none focus:border-accent"
                />
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  placeholder="-"
                  value={peStr}
                  onChange={e => updateLevel(key, 'pe', e.target.value)}
                  className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm focus:outline-none focus:border-accent"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="-"
                  value={pbStr}
                  onChange={e => updateLevel(key, 'pb', e.target.value)}
                  className="bg-paper-card border border-rule rounded px-2 py-1 text-right font-mono text-sm focus:outline-none focus:border-accent"
                />
                <div className="text-center">
                  {hit ? (
                    <span title="当前价已触发此档" className="text-amber-400 text-xs">●</span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>

        {/* 对接文档（默认折叠，给外部 agent 对接用） */}
        <details className="border border-rule rounded">
          <summary className="px-3 py-2 cursor-pointer text-sm select-none flex items-center justify-between bg-paper-tint rounded">
            <span>📄 对接文档 · 外部 agent batch 接口</span>
            <span className="text-[11px] text-ink-muted">点击展开 / 收起</span>
          </summary>
          <div className="px-3 py-3 space-y-2">
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleCopyDoc}
                className="text-xs px-2 py-1 rounded border border-rule hover:bg-paper-tint bg-paper-card"
              >
                {copied ? '✓ 已复制' : '复制全部'}
              </button>
            </div>
            <pre className="text-[11px] font-mono whitespace-pre-wrap bg-paper-deep p-3 rounded overflow-x-auto text-ink">
              {AGENT_DOC_TEXT}
            </pre>
          </div>
        </details>

        {/* 启用监控 */}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={e => setEnabled(e.target.checked)}
            className="w-4 h-4 accent-indigo-500"
          />
          <span>启用监控（触发时推送钉钉）</span>
        </label>

        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-200 px-3 py-2 rounded text-sm">
            {error}
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex items-center justify-between pt-2">
          <div>
            <Button
              variant="ghost"
              onClick={handleClear}
              disabled={saving || !currentConfig}
              className="text-red-400 hover:text-red-300"
            >
              清除挡位
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
 * 检查 4 档价格是否满足"重仓 < 加仓 < 减仓 < 全卖"
 * 返回警告字符串（不满足时）；返回空串表示 OK
 */
function checkLevelOrder(levels: AlertLevels): string {
  const warnings: string[] = [];
  const pairs: Array<[LevelKey, LevelKey, string]> = [
    ['heavy_position', 'add_position', '加仓价应高于重仓价'],
    ['add_position', 'reduce_position', '减仓价应高于加仓价'],
    ['reduce_position', 'full_exit', '全卖价应高于减仓价'],
  ];
  for (const [a, b, msg] of pairs) {
    const la = levels[a];
    const lb = levels[b];
    if (la && lb && la.price > 0 && lb.price > 0 && la.price >= lb.price) {
      warnings.push(`· ${msg}（${la.price} ≥ ${lb.price}）`);
    }
  }
  return warnings.join('\n');
}
