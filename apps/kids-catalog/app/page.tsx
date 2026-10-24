"use client";
import {Suspense,useCallback,useEffect,useState,type FormEvent} from "react";
import {usePathname,useRouter,useSearchParams} from "next/navigation";
import DevicePlaylist from "./device-playlist";
type Album={id:number;platform:string;title:string;url:string;age_evidence:string;age_confidence:string;sale_type?:number|null;source?:string;download_status:string;downloaded_tracks?:number;total_tracks?:number;track_count?:number|null;size_bytes?:number|null;reason?:string;last_seen?:string};
type Tab="catalog"|"playlist";
export default function Home(){
 // useSearchParams 需要 Suspense 边界，否则静态构建会报错。
 return <Suspense fallback={<main><p role="status">正在打开宝宝音频库…</p></main>}><KidsCatalog/></Suspense>;
}
function KidsCatalog(){
 const router=useRouter();const pathname=usePathname();const params=useSearchParams();
 const tab:Tab=params.get("tab")==="playlist"?"playlist":"catalog";
 const switchTab=(next:Tab)=>router.push(`${pathname}?tab=${next}`,{scroll:false});
 const [albums,setAlbums]=useState<Album[]>([]);const [refreshing,setRefreshing]=useState(false);const [message,setMessage]=useState("");const [link,setLink]=useState("");const [importing,setImporting]=useState(false);
 const load=useCallback(async()=>{const response=await fetch("/api/kids/albums",{cache:"no-store"});if(!response.ok)throw new Error("目录读取失败");const data=await response.json();setAlbums(data.albums)},[]);
 useEffect(()=>{load().catch(e=>setMessage(e.message))},[load]);
 const busy=albums.some(x=>x.download_status==="queued"||x.download_status==="running");
 useEffect(()=>{if(!busy)return;const timer=setInterval(()=>load().catch(()=>{}),3000);return()=>clearInterval(timer)},[busy,load]);
 const downloadLabel=(x:Album)=>x.download_status==="not_downloaded"?"下载":x.download_status==="queued"?"排队中":x.download_status==="running"?`下载中 ${x.downloaded_tracks??0}/${x.total_tracks??0}`:x.download_status==="partial"?"部分完成":x.download_status==="skipped_paid"?"付费跳过":x.download_status==="failed"?"重试":x.download_status==="done"?"已下载":x.download_status==="unavailable"?"已下架":`未知(${x.download_status})`;
 // 导入结果按后端返回的 job 状态措辞，重复导入已完成的专辑不说「开始下载」。
 const importMessage=(d:{title?:string;status?:string})=>d.status==="done"?`《${d.title}》已在目录中，无需重复下载`:d.status==="running"?`《${d.title}》正在下载中`:d.status==="queued"?`《${d.title}》已排队，等待下载`:d.status==="partial"?`《${d.title}》部分下载完成`:d.status==="failed"?`《${d.title}》下载失败，可在卡片上点重试`:d.status==="unavailable"?`《${d.title}》已被平台下架`:d.status==="skipped_paid"?`《${d.title}》为付费专辑，已跳过`:`《${d.title}》开始下载`;
 // 曲数优先用下载时的实际列表数，未下载时用采集时的平台总数；大小只在有文件时显示。
 const trackBadge=(x:Album)=>x.total_tracks||x.track_count||0;
 const sizeBadge=(x:Album)=>x.size_bytes&&x.size_bytes>0?`${(x.size_bytes/1048576).toFixed(1)} MB`:"";
 const refresh=async()=>{setRefreshing(true);setMessage("");try{const response=await fetch("/api/kids/refresh",{method:"POST"});const data=await response.json();if(!response.ok)throw new Error(data.detail||"获取失败");await load();setMessage(`已获取 ${data.count} 个最新候选`)}catch(e){setMessage(e instanceof Error?e.message:"获取失败")}finally{setRefreshing(false)}};
 const queue=async(id:number)=>{await fetch(`/api/kids/albums/${id}/download`,{method:"POST"});await load()};
 // 手动导入：解析→预检→入目录→自动下载一步到位，失败原因由后端原样透出。
 // detail 可能是字符串（业务拒绝）或数组（请求体校验失败），两种都要给出可读原因。
 const detailText=(d:unknown)=>typeof d==="string"?d:Array.isArray(d)&&d.length?String((d[0]as{msg?:string}).msg||"请求参数不合法"):"获取失败";
 const importAlbum=async(e:FormEvent<HTMLFormElement>)=>{e.preventDefault();const url=link.trim();if(!url)return;setImporting(true);setMessage("");try{const response=await fetch("/api/kids/albums/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url})});const data=await response.json();if(!response.ok)throw new Error(detailText(data.detail));setLink("");await load();setMessage(importMessage(data))}catch(e){setMessage(e instanceof Error?e.message:"获取失败")}finally{setImporting(false)}};
 // last_seen 为后端本地时间 ISO 字符串，切片读取避免跨时区换算偏移。
 // 标题只认榜单来源：手动专辑的 last_seen 是导入时间，会把月份标题顶到导入当月。
 const chartStamp=albums.filter(x=>x.source==="chart").map(x=>x.last_seen??"").sort().at(-1)??"";
 const stamp=chartStamp||(albums.map(x=>x.last_seen??"").sort().at(-1)??"");
 const heading=stamp?`${+stamp.slice(0,4)}年${+stamp.slice(5,7)}月精选`:"本月精选";
 const updated=stamp&&`更新于 ${+stamp.slice(5,7)}月${+stamp.slice(8,10)}日 ${stamp.slice(11,16)}`;
 return <main><a className="back" href="/">← 返回首页</a><nav className="tabs" aria-label="页面切换"><button type="button" className="tab" aria-current={tab==="catalog"?"page":undefined} onClick={()=>switchTab("catalog")}>本月精选</button><button type="button" className="tab" aria-current={tab==="playlist"?"page":undefined} onClick={()=>switchTab("playlist")}>设备歌单</button></nav><header><div><span>宝宝音频库 · 0–1岁</span><h1>{tab==="catalog"?heading:"设备歌单"}</h1><small>{tab==="catalog"?"平台明确年龄依据的专辑，以及手动添加的合集":"按编号把本月已下载的合集交给设备"}</small>{tab==="catalog"&&updated&&<small>{updated}</small>}</div>{tab==="catalog"&&<button className="refresh" disabled={refreshing} onClick={refresh}>{refreshing?"正在获取…":"获取最新"}</button>}</header>{tab==="playlist"?<DevicePlaylist/>:<><form className="import" onSubmit={importAlbum}><input type="text" inputMode="url" aria-label="专辑链接" placeholder="粘贴专辑链接（喜马拉雅 / 蜻蜓FM）" value={link} onChange={e=>setLink(e.target.value)}/><button type="submit" disabled={importing||!link.trim()}>{importing?"正在导入…":"获取"}</button></form>{message&&<p className="message">{message}</p>}{albums.length===0&&!refreshing&&<section className="empty"><h2>还没有本月候选</h2><p>点击“获取最新”，从平台公开目录生成列表；或在上方粘贴专辑链接手动添加。</p></section>}<section>{albums.map(x=><article key={x.id} className={x.download_status==="unavailable"?"offline":""}><div><b>{x.platform}</b><a href={x.url} target="_blank" rel="noreferrer">{x.title}{x.source==="manual"&&<span className="badge manual">手动添加</span>}{x.sale_type===0&&<span className="badge free">免费</span>}{x.sale_type===1&&<span className="badge vip">会员畅听</span>}{x.sale_type==null&&<span className="badge unknown" title="该平台未提供付费信息">付费未知</span>}{trackBadge(x)>0&&<span className="badge tracks" title="整张专辑曲目总数（下载成本预估）">{trackBadge(x)} 曲</span>}{sizeBadge(x)&&<span className="badge size" title="已下载文件占用磁盘空间">{sizeBadge(x)}</span>}</a><small>{x.source==="manual"?"用户自主选择 · 不做年龄筛选":`${x.age_evidence} · ${x.age_confidence}可信`}</small>{x.reason&&<small>{x.reason}</small>}</div><button disabled={x.download_status!=="not_downloaded"&&x.download_status!=="failed"&&x.download_status!=="needs_authorization"} onClick={()=>queue(x.id)}>{downloadLabel(x)}</button></article>)}</section></>}</main>;
}
