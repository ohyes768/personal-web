"use client";

export type Candidate = {folder: string; title: string; confirmed: boolean; track_count: number};

type CandidatePickerProps = {candidates: Candidate[]; unchecked: Set<string>; disabled: boolean;
  onToggle: (folder: string) => void; onSetAll: (checked: boolean) => void;
  onConfirm: (candidate: Candidate) => void; confirming: string | null};

export default function CandidatePicker({candidates, unchecked, disabled, onToggle, onSetAll, onConfirm, confirming}: CandidatePickerProps) {
  const selectedCount = candidates.filter(row => !unchecked.has(row.folder)).length;
  const allSelected = selectedCount === candidates.length;
  return <section className="playlist-candidates" aria-labelledby="candidate-heading">
    <div className="candidates-head">
      <h3 id="candidate-heading">选择要加入歌单的合集（{selectedCount}/{candidates.length}）</h3>
      {candidates.length > 0 && <button className="secondary toggle-all" disabled={disabled}
        onClick={() => onSetAll(!allSelected)}>{allSelected ? "全不选" : "全选"}</button>}
    </div>
    {candidates.length === 0 && <p className="playlist-empty">还没有可加入歌单的合集，先下载音频；主动精简的合集也会显示在这里。</p>}
    {candidates.some(row => !row.confirmed) && <p className="playlist-note">未确认的合集请先点击“确认保留曲目”，再生成歌单。主动删曲后也按当前保留文件核对。</p>}
    <ul className="candidate-list">
      {candidates.map(row => <li key={row.folder} className="candidate-row">
        <label>
          <input type="checkbox" checked={!unchecked.has(row.folder)} disabled={disabled}
            onChange={() => onToggle(row.folder)} />
          <span className="candidate-title">{row.title}</span>
        </label>
        {row.track_count > 0 && <span className="badge tracks"
          title={row.confirmed ? "完成台账记录的曲目数，生成时按此发布" : "以下载数估计，生成时以实际文件校验为准"}>{row.track_count} 首</span>}
        {!row.confirmed && <>
          <span className="badge unconfirmed" title="当前保留曲目尚未确认，生成时会跳过">未确认</span>
          <button className="secondary" disabled={disabled || confirming !== null}
            onClick={() => onConfirm(row)}>{confirming === row.folder ? "正在核对…" : "确认保留曲目"}</button>
        </>}
      </li>)}
    </ul>
  </section>;
}
