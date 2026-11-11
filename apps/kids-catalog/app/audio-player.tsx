"use client";

import {useEffect, useState} from "react";

type Track = {file: string; title: string};

type CollectionPlayerProps = {folder: string; title: string; onClose: () => void};

// 设备歌单浏览器播放：nginx /kids-audio/ 直接服务合集音频（Range 支持拖动进度）。
// 中文目录/文件名必须逐段 encodeURIComponent，否则 <audio src> 会 404。
function trackUrl(folder: string, file: string) {
  return `/kids-audio/${encodeURIComponent(folder)}/${encodeURIComponent(file)}`;
}

// 底部悬浮播放条：固定在视口底部，页面级单例。
// 切 tab / 离开页面时组件卸载 → 音频停止（不做跨页续播）。
export default function CollectionPlayer({folder, title, onClose}: CollectionPlayerProps) {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);

  useEffect(() => {
    let active = true;
    // 换合集即换源：旧曲目状态不能带到新合集（组件也可能被复用而没卸载）。
    setTracks(null);
    setError("");
    setIndex(0);
    fetch(`/api/kids/collections/${encodeURIComponent(folder)}/tracks`, {cache: "no-store"})
      .then(async response => {
        const data = await response.json();
        if (!active) return;
        if (!response.ok) {
          throw new Error(typeof data.detail === "string" ? data.detail
            : data.detail?.message || "曲目列表读取失败");
        }
        setTracks(data.tracks);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "曲目列表读取失败");
      });
    return () => {active = false;};
  }, [folder]);

  if (error) {
    return <div className="player-dock" role="status">
      <div className="player-dock-inner">
        <span className="player-dock-error">{error}</span>
        <button type="button" className="secondary" onClick={onClose}>收起</button>
      </div>
    </div>;
  }
  if (tracks === null) {
    return <div className="player-dock" role="status">
      <div className="player-dock-inner"><span>正在读取曲目列表…</span></div>
    </div>;
  }
  const current = tracks[index];
  const last = tracks.length - 1;
  // 顺序播完即止：最后一首结束时不再前进（没有下一首时播放自然结束）。
  return <div className="player-dock">
    <div className="player-dock-inner">
      <div className="player-dock-info">
        <b title={title}>{title}</b>
        <small>{tracks.length
          ? `${index + 1}/${tracks.length} 首${current ? ` · ${current.title}` : ""}`
          : "没有可播放的音频"}</small>
      </div>
      <audio key={current?.file ?? ""} src={current ? trackUrl(folder, current.file) : undefined}
        controls autoPlay preload="none" playsInline
        onEnded={() => setIndex(i => (i < last ? i + 1 : i))}/>
      <div className="player-dock-actions">
        <button type="button" className="secondary" disabled={index === 0}
          onClick={() => setIndex(i => Math.max(0, i - 1))}>上一首</button>
        <button type="button" className="secondary" disabled={tracks.length === 0 || index >= last}
          onClick={() => setIndex(i => Math.min(last, i + 1))}>下一首</button>
        {tracks.length > 1 && <details className="player-dock-tracks">
          <summary>曲目</summary>
          <ol>{tracks.map((track, i) => <li key={track.file}>
            <button type="button" className={i === index ? "current" : ""} onClick={() => setIndex(i)}>
              {track.title}
            </button>
          </li>)}</ol>
        </details>}
        <button type="button" className="secondary" onClick={onClose}>收起</button>
      </div>
    </div>
  </div>;
}
