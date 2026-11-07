"use client";

import {useCallback, useEffect, useState} from "react";

type Track = {file: string; title: string};

type CollectionPlayerProps = {folder: string; title: string; onClose: () => void};

// 设备歌单浏览器播放：nginx /kids-audio/ 直接服务合集音频（Range 支持拖动进度）。
// 中文目录/文件名必须逐段 encodeURIComponent，否则 <audio src> 会 404。
function trackUrl(folder: string, file: string) {
  return `/kids-audio/${encodeURIComponent(folder)}/${encodeURIComponent(file)}`;
}

export default function CollectionPlayer({folder, title, onClose}: CollectionPlayerProps) {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [error, setError] = useState("");
  const [index, setIndex] = useState(0);

  useEffect(() => {
    let active = true;
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

  const next = useCallback(() => setIndex(i => i + 1), []);

  if (error) {
    return <div className="player" role="status">{error} <button type="button" className="secondary"
      onClick={onClose}>收起</button></div>;
  }
  if (tracks === null) return <div className="player" role="status">正在读取曲目列表…</div>;
  const current = tracks[index];
  // 顺序播完即止：没有下一首时不再设置 src，播放自然结束。
  return <div className="player">
    <audio key={current?.file ?? ""} src={current ? trackUrl(folder, current.file) : undefined}
      controls autoPlay preload="none" onEnded={() => {if (index < tracks.length - 1) next();}}/>
    <div className="player-head">
      <b>正在播放：{title}</b>
      <small>{tracks.length ? `${index + 1}/${tracks.length} 首` : "没有可播放的音频"}</small>
      <button type="button" className="secondary" onClick={onClose}>收起</button>
    </div>
    {tracks.length > 1 && <ol className="player-tracks">{tracks.map((track, i) => <li key={track.file}>
      <button type="button" className={i === index ? "current" : ""} onClick={() => setIndex(i)}>
        {track.title}
      </button>
    </li>)}</ol>}
  </div>;
}
