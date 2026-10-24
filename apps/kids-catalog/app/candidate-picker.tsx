"use client";

export type Candidate = {folder: string; title: string; confirmed: boolean; track_count: number};

type CandidatePickerProps = {candidates: Candidate[]; unchecked: Set<string>; disabled: boolean;
  onToggle: (folder: string) => void; onSetAll: (checked: boolean) => void};

export default function CandidatePicker({candidates, unchecked, disabled, onToggle, onSetAll}: CandidatePickerProps) {
  const selectedCount = candidates.filter(row => !unchecked.has(row.folder)).length;
  const allSelected = selectedCount === candidates.length;
  return <section className="playlist-candidates" aria-labelledby="candidate-heading">
    <div className="candidates-head">
      <h3 id="candidate-heading">选择要加入歌单的合集（{selectedCount}/{candidates.length}）</h3>
      {candidates.length > 0 && <button className="secondary toggle-all" disabled={disabled}
        onClick={() => onSetAll(!allSelected)}>{allSelected ? "全不选" : "全选"}</button>}
    </div>
    {candidates.length === 0 && <p className="playlist-empty">本月还没有已下载完成的合集，先到“本月精选”下载。</p>}
    {candidates.some(row => !row.confirmed) && <p className="playlist-note">标为“未确认”的合集还没核对过下载是否完整，勾选后生成时仍可能被跳过。</p>}
    <ul className="candidate-list">
      {candidates.map(row => <li key={row.folder} className="candidate-row">
        <label>
          <input type="checkbox" checked={!unchecked.has(row.folder)} disabled={disabled}
            onChange={() => onToggle(row.folder)} />
          <span className="candidate-title">{row.title}</span>
        </label>
        {row.track_count > 0 && <span className="badge tracks"
          title={row.confirmed ? "完成台账记录的曲目数，生成时按此发布" : "以下载数估计，生成时以实际文件校验为准"}>{row.track_count} 首</span>}
        {!row.confirmed && <span className="badge unconfirmed" title="完成台账里还没有确认记录，生成时以实际文件校验为准">未确认</span>}
      </li>)}
    </ul>
  </section>;
}
