"use client";

import {useCallback, useEffect, useState} from "react";

type Entry = {number: number; title: string; track_count: number};
type Snapshot = {revision: string; generated_at: string; items: Entry[]};
type Skipped = {title: string; folder?: string; reason: string; code: string};
type Candidate = {folder: string; title: string; confirmed: boolean};
type DirectoryState = {
  snapshot: Snapshot | null;
  generation: {status: "idle" | "running" | "done" | "failed"; error: string | null; skipped: Skipped[]};
  candidates?: Candidate[];
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/kids/collections${path}`, {cache: "no-store", ...options});
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "歌单操作失败，请重试");
  }
  return data;
}

export default function DevicePlaylist() {
  const [state, setState] = useState<DirectoryState | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  // 只记取消勾选的合集：新出现的合集默认勾上，用户的取消不会因刷新丢失。
  const [unchecked, setUnchecked] = useState<Set<string>>(new Set());
  const load = useCallback(async () => {
    const next = await request<DirectoryState>("");
    setState(next);
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    request<DirectoryState>("").then(next => {
      if (active) setState(next);
    }).catch(() => {
      if (active) setMessage("设备歌单读取失败，请重新读取或稍后重试。");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const running = state?.generation.status === "running";
  useEffect(() => {
    if (!running) return;
    let active = true;
    const timer = setInterval(() => {
      request<DirectoryState>("").then(next => {
        if (active) {setState(next); setMessage("");}
      }).catch(() => {
        if (active) setMessage("暂时无法读取生成结果，正在重试；屏幕仍使用上一份歌单。");
      });
    }, 2000);
    return () => {active = false; clearInterval(timer);};
  }, [running]);

  const candidates = state?.candidates ?? [];
  const selection = candidates.filter(row => !unchecked.has(row.folder)).map(row => row.folder);
  const toggle = (folder: string) => {
    setUnchecked(previous => {
      const next = new Set(previous);
      if (next.has(folder)) next.delete(folder); else next.add(folder);
      return next;
    });
  };

  const generate = async () => {
    if (selection.length === 0) {
      setMessage("请至少选择一个合集再生成歌单。");
      return;
    }
    setSubmitting(true);
    setMessage("");
    try {
      await request("/generate", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({folders: selection})});
      // Keep polling even when the first status request fails after acceptance.
      setState(previous => ({snapshot: previous?.snapshot ?? null,
        generation: {status: "running", error: null, skipped: []}}));
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "生成歌单失败，请重试");
      await load().catch(() => {});
    } finally {
      setSubmitting(false);
    }
  };

  const confirm = async (item: Skipped) => {
    const folder = item.folder ?? item.title;
    setConfirming(folder);
    setMessage("");
    try {
      await request("/confirm", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({folder})});
      // 确认只写完成台账，重新读取让候选清单的“未确认”标记跟上；跳过项仍在服务端记录里。
      await load().catch(() => {});
      setMessage(`已确认“${item.title}”下载完整。点击“生成歌单”更新设备清单。`);
      setState(previous => previous ? {...previous, generation: {...previous.generation,
        skipped: previous.generation.skipped.filter(row => row.title !== item.title)}} : previous);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "确认失败，请重试");
    } finally {
      setConfirming(null);
    }
  };

  const snapshot = state?.snapshot;
  return <section className="device-playlist" aria-labelledby="device-playlist-heading" aria-busy={loading || running || submitting}>
    <div className="playlist-heading">
      <div>
        <span className="eyebrow">屏幕上的播放清单</span>
        <h2 id="device-playlist-heading">生成设备歌单</h2>
        <p>勾选本月已下载完成的合集，曲目少的排在前面。</p>
      </div>
      <button disabled={loading || submitting || running || confirming !== null} onClick={generate}>
        {submitting || running ? "正在生成…" : "生成歌单"}
      </button>
    </div>
    <p className="playlist-note">重新生成后，编号可能调整。设备按同一版本的编号查询专辑名称。</p>
    {loading && <p role="status">正在读取设备歌单…</p>}
    {message && <p className="message" role="status">{message}</p>}
    {!loading && !state && <button className="secondary" onClick={() => load().then(() => setMessage("")).catch(() => setMessage("歌单读取失败，请稍后重试"))}>重新读取</button>}
    {state?.generation.error && <p className="message" role="alert">{state.generation.error}</p>}
    {running && <p role="status">正在检查本月已下载音频并统计曲目数，完成前继续使用上一份歌单。</p>}
    {!loading && <section className="playlist-candidates" aria-labelledby="candidate-heading">
      <h3 id="candidate-heading">选择要加入歌单的合集（{selection.length}/{candidates.length}）</h3>
      {candidates.length === 0 && <p className="playlist-empty">本月还没有已下载完成的合集，先到“本月精选”下载。</p>}
      {candidates.some(row => !row.confirmed) && <p className="playlist-note">标为“未确认”的合集还没核对过下载是否完整，勾选后生成时仍可能被跳过。</p>}
      <ul className="candidate-list">
        {candidates.map(row => <li key={row.folder} className="candidate-row">
          <label>
            <input type="checkbox" checked={!unchecked.has(row.folder)} disabled={running || submitting}
              onChange={() => toggle(row.folder)} />
            <span className="candidate-title">{row.title}</span>
          </label>
          {!row.confirmed && <span className="badge unconfirmed" title="完成台账里还没有确认记录，生成时以实际文件校验为准">未确认</span>}
        </li>)}
      </ul>
    </section>}
    {snapshot ? <>
      <h3 className="playlist-subheading">当前设备歌单</h3>
      <div className="playlist-stamp">{snapshot.items.length} 个合集 · 生成于 {new Date(snapshot.generated_at).toLocaleString("zh-CN")}</div>
      <div className="playlist-table-wrap"><table className="playlist-table">
        <caption className="visually-hidden">设备当前歌单，按曲目数从少到多排列</caption>
        <thead><tr><th scope="col">编号</th><th scope="col">合集名称</th><th scope="col">曲目数</th></tr></thead>
        <tbody>{snapshot.items.map(item => <tr key={item.number}>
          <td className="playlist-number">{item.number}</td><td>{item.title}</td><td>{item.track_count} 首</td>
        </tr>)}</tbody>
      </table></div>
    </> : !loading && <p className="playlist-empty">还没有设备歌单。下载完成后，勾选合集并点击“生成歌单”。</p>}
    {!!state?.generation.skipped.length && <details className="playlist-skipped" open>
      <summary>未加入歌单的合集（{state.generation.skipped.length}）</summary>
      <ul>{state.generation.skipped.map(item => <li key={item.title}>
        <div><strong>{item.title}</strong><small>{item.reason}</small></div>
        {item.code === "unconfirmed" && <button className="secondary" disabled={running || submitting || confirming !== null}
          onClick={() => confirm(item)}>{confirming === (item.folder ?? item.title) ? "正在核对…" : "确认此合集已下载完整"}</button>}
      </li>)}</ul>
    </details>}
  </section>;
}
