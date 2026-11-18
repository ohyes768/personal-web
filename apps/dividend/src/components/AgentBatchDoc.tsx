'use client';

import { useState } from 'react';

// 外部 agent 调用挡位批量接口的对接文档。
// 原先整段铺在挡位设置弹框里（635px 长文 + 复制按钮），与「配挡位」主任务无关；
// 挪进数据更新抽屉做默认折叠块——需要对接的运维打开才看到。
const BATCH_DOC_TEXT = `POST /api/dividend/favorites/alerts/batch
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
- 4 档 price 必填 > 0；pe/pb 选填
- code 必须已收藏（POST /api/dividend/favorites/{code}）；未收藏 → 该条 fail，不会自动加入
- 每条独立处理，部分失败不影响其他
- 缺/错 token → 401；服务端未配 AGENT_API_TOKEN → 503`;

export function AgentBatchDoc() {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(BATCH_DOC_TEXT);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API 在非 HTTPS / 旧浏览器可能失败，静默忽略
    }
  };

  return (
    <details className="rounded-lg border border-rule bg-paper-card">
      <summary className="cursor-pointer select-none px-3 py-2.5 text-[13px] font-medium text-ink hover:text-accent">
        外部 Agent：批量更新挡位
      </summary>
      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={handleCopy}
          className="mb-2 rounded border border-rule-strong bg-paper-tint px-2.5 py-1 text-xs font-medium text-ink hover:border-info hover:text-info"
        >
          {copied ? '已复制' : '复制全文'}
        </button>
        <pre className="max-h-72 overflow-auto whitespace-pre rounded border border-rule bg-paper px-3 py-2 text-[11px] leading-relaxed text-ink-soft">
          {BATCH_DOC_TEXT}
        </pre>
      </div>
    </details>
  );
}
