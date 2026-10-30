import { DirectorySourceCard, type Source } from './DirectoryCards';

export function CatalogTmsfDetails({ sources, busy, updating, collecting, onUpdate }: {
  sources?: Source[]; busy: boolean; updating: boolean; collecting: boolean; onUpdate: () => void;
}) {
  const records = sources?.filter(s => s.source === 'tmsf') || [];
  const available = records.some(s => s.status !== 'ignored');
  return <section className="directory-source-section" aria-label="透明售房网资料" aria-busy={updating}>
    <div className="directory-source-section-heading"><h4>透明售房网资料</h4>
      <button className="btn btn-secondary" disabled={busy || updating || collecting || !available} onClick={onUpdate}>
        {updating ? '正在更新透明售房网资料…' : '更新透明售房网资料'}
      </button>
    </div>
    <p className="directory-muted">重新获取用途、地址、挂牌数量及新房 / 二手房身份，更新后重新判断收录状态。</p>
    {collecting && <p role="status" className="directory-muted">透明售房网正在批量采集，请完成后更新。</p>}
    {records.length ? records.map(s => <DirectorySourceCard key={s.id} item={s} compact />)
      : <p className="directory-muted">暂无透明售房网来源，请先采集住宅名称。</p>}
  </section>;
}
