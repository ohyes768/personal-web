"use client";
import {useCallback,useEffect,useState} from "react";
type Track={file:string;title:string;size:number};
type Props={album:{id:number;title:string};onClose:()=>void;onChanged:()=>void};
const fmt=(n:number)=>n>=1048576?`${(n/1048576).toFixed(1)} MB`:n>0?`${Math.max(1,Math.round(n/1024))} KB`:"";
// 已下载曲目管理弹窗：目录即事实源，删除直接删文件；误删可通过「补全下载」找回。
export default function TrackManager({album,onClose,onChanged}:Props){
 const [tracks,setTracks]=useState<Track[]|null>(null);
 const [error,setError]=useState("");
 const [busy,setBusy]=useState("");
 const load=useCallback(async()=>{const response=await fetch(`/api/kids/albums/${album.id}/tracks`,{cache:"no-store"});if(!response.ok)throw new Error("曲目读取失败");const data=await response.json();setTracks(data.tracks)},[album.id]);
 useEffect(()=>{load().catch(e=>setError(e instanceof Error?e.message:"曲目读取失败"))},[load]);
 const remove=async(file:string)=>{setBusy(file);setError("");try{const response=await fetch(`/api/kids/albums/${album.id}/tracks`,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({file})});const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"删除失败");await load();onChanged()}catch(e){setError(e instanceof Error?e.message:"删除失败")}finally{setBusy("")}};
 return <div className="modal-overlay" onClick={onClose} role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label={`管理《${album.title}》曲目`} onClick={e=>e.stopPropagation()}>
  <header className="modal-head"><b>《{album.title}》</b><button type="button" className="modal-close" onClick={onClose} aria-label="关闭">×</button></header>
  {tracks===null?<p role="status" className="modal-tip">正在读取曲目…</p>:tracks.length===0?<p className="modal-tip">该专辑还没有下载文件。</p>:<ul className="track-list">{tracks.map(t=><li key={t.file}><span className="track-title">{t.title}</span><span className="track-size">{fmt(t.size)}</span><button type="button" className="secondary track-delete" disabled={busy===t.file} onClick={()=>remove(t.file)}>{busy===t.file?"删除中…":"删除"}</button></li>)}</ul>}
  {error&&<p className="message">{error}</p>}
  <footer><small className="modal-tip">删除的曲目可通过「补全下载」找回（已下载的文件不会重复下载）；已生成设备歌单的合集，删除后需重新生成。</small></footer>
 </div></div>;
}
