'use client';

import { useState } from 'react';
import { workflowRequest, type CatalogRow } from './DirectoryFlowWorkspace';
import { marketLabels } from './DirectoryCards';
import { PositionBadge } from './PositionPanel';
import { rentalCoverageLabels, type CatalogCoverage } from './CatalogCoverage';
import DirectoryDialog from './DirectoryDialog';

type MergeOutcome = { id: string; name: string; ok: boolean; error?: string };

function auctionLine(value?: CatalogCoverage['auction']): string {
  return value?.round_count ? `法拍 ${value.round_count} 轮` : '暂无拍卖记录';
}

function rentalLine(value?: CatalogCoverage['rental']): string {
  if (!value) return '租金状态未知';
  return value.state === 'data' ? `租金样本 ${value.sample_count} 条` : `租金${rentalCoverageLabels[value.state] || '状态未知'}`;
}

/** 已收录小区多选合并弹框：单选保留方并预览并入库径；逐条调用合并接口，某条失败不回滚已成功项。 */
export default function MergeDialog({ rows, onClose, onMerged }: {
  rows: CatalogRow[]; onClose: () => void; onMerged: () => void }) {
  const [keeperId, setKeeperId] = useState(() => {
    const ranked = [...rows].sort((a, b) => Number(!!b.position?.has_coordinates) - Number(!!a.position?.has_coordinates)
      || (b.sources?.length || 0) - (a.sources?.length || 0));
    return ranked[0]?.community_id || '';
  });
  const [phase, setPhase] = useState<'preview' | 'running' | 'done'>('preview');
  const [results, setResults] = useState<MergeOutcome[]>([]);
  const keeper = rows.find(r => r.community_id === keeperId) || rows[0];
  const others = rows.filter(r => r.community_id !== keeper?.community_id);
  const mixedMarket = new Set(rows.map(r => r.market_state || 'unknown')).size > 1;
  async function submit() {
    if (!keeper || phase !== 'preview') return;
    setPhase('running');
    for (const row of others) {
      try {
        await workflowRequest(`/directory/communities/${encodeURIComponent(row.community_id)}/merge`, 'POST', { community_id: keeper.community_id });
        setResults(v => [...v, { id: row.community_id, name: row.community_name, ok: true }]);
      } catch (e) {
        setResults(v => [...v, { id: row.community_id, name: row.community_name, ok: false,
          error: e instanceof Error ? e.message : '合并失败，请重试' }]);
      }
    }
    setPhase('done');
    onMerged();
  }
  return <DirectoryDialog title="合并所选小区" onClose={onClose}
    footer={phase !== 'done' && <div className="directory-actions">
      <button className="btn btn-primary" disabled={phase === 'running'} onClick={() => void submit()}>
        {phase === 'running' ? '正在合并…' : `确认合并${mixedMarket ? '（保留方市场状态将生效）' : ''}`}
      </button></div>}>
    {mixedMarket && <p className="directory-warning">所选小区的新房 / 二手房状态不一致，合并后沿用保留方的市场状态，请核对保留方选择。</p>}
    <section aria-label="选择保留方"><h4>选择保留方</h4>
      {rows.map(row => <label className="merge-row" key={row.community_id}>
        <input type="radio" name="merge-keeper" disabled={phase !== 'preview'} checked={row.community_id === keeper?.community_id}
          onChange={() => setKeeperId(row.community_id)} />
        <span className="merge-row-body"><strong>{row.community_name}</strong>
          <small>{row.district || '区域待补'} · {row.address || '地址待主体匹配'}</small>
          <small>来源 {row.sources?.length || 0} 条 · {auctionLine(row.coverage?.auction)} · {rentalLine(row.coverage?.rental)}</small>
          <small className="catalog-inline"><PositionBadge position={row.position} compact />
            <span className={mixedMarket ? 'merge-market-mixed' : undefined}>{marketLabels[row.market_state || 'unknown'] || marketLabels.unknown}</span></small>
        </span>
      </label>)}
    </section>
    {keeper && <section className="merge-preview" aria-label="合并预览"><h4>合并预览</h4>
      <p>以下 {others.length} 条将并入「{keeper.community_name}」，完成后被并方记录从列表消失：</p>
      {others.map(row => <div key={row.community_id}><strong>{row.community_name}</strong>
        <small>名称{row.aliases?.length ? `、别名（${row.aliases.join(' / ')}）` : ''}将并入保留方别名</small>
        <small>地址：{keeper.address ? `沿用保留方「${keeper.address}」，被并方地址不覆盖` : row.address ? `保留方缺失，将补入「${row.address}」` : '双方地址均待补'}</small>
        <small>坐标：{keeper.position?.has_coordinates ? '沿用保留方坐标，不覆盖'
          : row.position?.has_coordinates ? '保留方缺坐标，将补入被并方经纬度' : '双方均缺坐标'}</small>
        <small>记录迁移：来源 {row.sources?.length || 0} 条 · {auctionLine(row.coverage?.auction)} · {rentalLine(row.coverage?.rental)}</small>
      </div>)}
      <small>高德 POI 匹配结果不随合并迁移，合并后如需定位请在保留方重新核对。</small>
    </section>}
    {phase !== 'preview' && <section className="merge-preview" aria-live="polite" aria-label="合并结果"><h4>合并结果</h4>
      {results.map(r => <p className="merge-result" data-ok={r.ok} key={r.id}>{r.ok ? '已合并' : '合并失败'}：{r.name}{r.error ? ` · ${r.error}` : ''}</p>)}
      {phase === 'running' && <p role="status" className="directory-muted">正在逐条合并…</p>}
      {phase === 'done' && !!results.length && results.every(r => r.ok) && <p role="status">全部合并完成，列表已刷新。</p>}
      {phase === 'done' && results.some(r => !r.ok) && <p className="directory-warning">失败项仍在列表中，可重新勾选后重试。</p>}
    </section>}
  </DirectoryDialog>;
}
