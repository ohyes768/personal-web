"use client";

import {useCallback, useEffect, useState} from "react";

type Entry = {number: number; title: string; track_count: number};
type Snapshot = {revision: string; generated_at: string; items: Entry[]};
type Skipped = {title: string; folder?: string; reason: string; code: string};
type DirectoryState = {
  snapshot: Snapshot | null;
  generation: {status: "idle" | "running" | "done" | "failed"; error: string | null; skipped: Skipped[]};
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

  const generate = async () => {
    setSubmitting(true);
    setMessage("");
    try {
      await request("/generate", {method: "POST"});
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
        <h2 id="device-playlist-heading">设备歌单</h2>
        <p>只生成本月已下载合集，曲目少的排在前面。</p>
      </div>
      <button disabled={loading || submitting || running || confirming !== null} onClick={generate}>
        {submitting || running ? "正在生成…" : "生成歌单"}
      </button>
    </div>
    <p className="playlist-note">重新生成后，编号可能调整，屏幕和播放映射会一起更新。</p>
    {loading && <p role="status">正在读取设备歌单…</p>}
    {message && <p className="message" role="status">{message}</p>}
    {!loading && !state && <button className="secondary" onClick={() => load().then(() => setMessage("")).catch(() => setMessage("歌单读取失败，请稍后重试"))}>重新读取</button>}
    {state?.generation.error && <p className="message" role="alert">{state.generation.error}</p>}
    {running && <p role="status">正在核对 NAS 合集与 MA 专辑，完成前继续使用上一份歌单。</p>}
    {snapshot ? <>
      <div className="playlist-stamp">{snapshot.items.length} 个合集 · 生成于 {new Date(snapshot.generated_at).toLocaleString("zh-CN")}</div>
      <div className="playlist-table-wrap"><table className="playlist-table">
        <caption className="visually-hidden">设备当前歌单，按曲目数从少到多排列</caption>
        <thead><tr><th scope="col">编号</th><th scope="col">合集名称</th><th scope="col">曲目数</th></tr></thead>
        <tbody>{snapshot.items.map(item => <tr key={item.number}>
          <td className="playlist-number">{item.number}</td><td>{item.title}</td><td>{item.track_count} 首</td>
        </tr>)}</tbody>
      </table></div>
    </> : !loading && <p className="playlist-empty">还没有设备歌单。下载完成后，点击“生成歌单”获取真实合集。</p>}
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
