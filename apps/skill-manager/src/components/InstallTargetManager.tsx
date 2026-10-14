'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createInstallTarget, listProfileCandidates, removeInstallTarget, renameInstallTarget, type ProfileCandidate } from '@/lib/api';
import type { InstallTarget } from '@/lib/installTargets';
import ConfirmActionDialog from './ConfirmActionDialog';

type Action = {kind:'new'} | {kind:'rename'|'delete'; target:InstallTarget};
interface Props {active:boolean; targets:InstallTarget[]; loading:boolean; error:string; onRefresh:()=>Promise<void>; onBoard:(id:InstallTarget['id'])=>void}
const button = 'rounded border border-slate-300 px-3 py-1.5 text-sm disabled:opacity-50';

export default function InstallTargetManager({active,targets,loading,error,onRefresh,onBoard}:Props) {
  const [profiles,setProfiles] = useState<ProfileCandidate[]>([]);
  const [profilesLoading,setProfilesLoading] = useState(false);
  const [profilesError,setProfilesError] = useState('');
  const [action,setAction] = useState<Action>();
  const [profile,setProfile] = useState('');
  const [name,setName] = useState('');
  const [confirming,setConfirming] = useState(false);
  const [busy,setBusy] = useState(false);
  const [actionError,setActionError] = useState('');
  const submitting = useRef(false);
  const loadGeneration = useRef(0);
  const mounted = useRef(true);
  useEffect(()=>{mounted.current=true; return ()=>{mounted.current=false;};},[]);
  const loadProfiles = useCallback(async()=>{
    const generation = ++loadGeneration.current;
    setProfilesLoading(true);setProfilesError('');
    try {const response=await listProfileCandidates(); if(mounted.current&&generation===loadGeneration.current) setProfiles(response.items);}
    catch(e) {if(mounted.current&&generation===loadGeneration.current) setProfilesError(e instanceof Error?e.message:'加载 profile 失败');}
    finally {if(mounted.current&&generation===loadGeneration.current) setProfilesLoading(false);}
  },[]);
  useEffect(()=>{if(active) void loadProfiles();},[active,loadProfiles]);
  const selected = profiles.find(p=>p.profile_name===profile);
  const close=()=>{if(!submitting.current){setAction(undefined);setConfirming(false);setActionError('');}};
  const open=(next:Action)=>{setAction(next);setConfirming(next.kind==='delete');setName(next.kind==='new'?'':next.target.name);setProfile('');setActionError('');if(next.kind==='new') void loadProfiles();};
  const save=async(password:string)=>{
    if(!action||submitting.current) return;
    submitting.current=true;setBusy(true);setActionError('');
    try {
      if(action.kind==='new') await createInstallTarget(profile,name.trim(),password);
      else if(action.kind==='rename') await renameInstallTarget(action.target.id,name.trim(),action.target.config_revision??1,password);
      else await removeInstallTarget(action.target.id,action.target.config_revision??1,password);
      if(mounted.current) {setAction(undefined);setConfirming(false);await onRefresh();await loadProfiles();}
    } catch(e) {if(mounted.current){setActionError(e instanceof Error?e.message:'保存失败');await onRefresh();}}
    finally {submitting.current=false;if(mounted.current) setBusy(false);}
  };
  const blocked = action?.kind==='delete' && (action.target.active_installation_count??0)>0;
  return <section className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
    <div className="flex items-center justify-between"><h2 className="font-semibold">安装目标</h2><button type="button" className={button} disabled={loading||!!error||busy} onClick={()=>open({kind:'new'})}>新增 profile 目标</button></div>
    <p className="text-xs text-slate-500">默认 Skill 目录固定；这里管理各 profile 的 skills 子目录。新增目标不会自动安装 Skill。</p>
    {loading&&<p>加载目标中…</p>}
    {error&&<p role="alert">{error}<button type="button" className={button} onClick={()=>void onRefresh()}>重试</button></p>}
    <ul className="grid gap-3 md:grid-cols-2">{targets.map(target=><li key={target.id} className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="font-medium">{target.name} {target.id==='hermes'&&<span className="text-xs text-slate-500">默认目录 · 只读</span>}</h3>
      <p className="text-xs text-slate-500">{target.profile_name}{target.removed?' · 已移除':''}</p>
      <p className="mt-2 break-all font-mono text-xs">{target.install_path}</p>
      <p className="mt-2 text-sm">{target.available?'可用':'不可用'} · 已安装 {target.active_installation_count??0} 个 Skill</p>
      {!target.available&&<p className="text-xs text-amber-700">{target.unavailable_reason}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {!!target.active_installation_count&&<button type="button" className={button} onClick={()=>onBoard(target.id)}>查看安装 / 下架</button>}
        {target.editable&&<><button type="button" className={button} disabled={busy} onClick={()=>open({kind:'rename',target})}>改名</button><button type="button" className={`${button} text-rose-700`} disabled={busy} onClick={()=>open({kind:'delete',target})}>删除目标</button></>}
      </div>
    </li>)}</ul>
    {action&&action.kind!=='delete'&&!confirming&&<div role="dialog" aria-modal="true" aria-label={action.kind==='new'?'新增安装目标':'修改目标名称'} className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <form className="w-full max-w-lg space-y-3 rounded-lg bg-white p-5" onSubmit={e=>{e.preventDefault();setConfirming(true);}}>
        <h2 className="font-semibold">{action.kind==='new'?'新增安装目标':'修改目标名称'}</h2>
        {action.kind==='new'?<>
          {profilesLoading&&<p>正在发现已有 profile…</p>}
          {profilesError&&<p role="alert">{profilesError}<button type="button" className={button} onClick={()=>void loadProfiles()}>重试</button></p>}
          <label className="block text-sm">选择已有 profile<select aria-label="选择已有 profile" className="mt-1 w-full rounded border p-2" value={profile} onChange={e=>{setProfile(e.target.value);setName(e.target.value);}} disabled={profilesLoading||!!profilesError} required><option value="">请选择</option>{profiles.map(p=><option key={p.profile_name} value={p.profile_name} disabled={!p.available||!!p.existing_target_id}>{p.profile_name}{p.existing_target_id?'（已登记）':p.available?'':`（${p.unavailable_reason}）`}</option>)}</select></label>
          {!profilesLoading&&!profilesError&&!profiles.length&&<p>授权目录下尚未发现 profile。请先在 Hermes 中准备环境和 skills 目录，再刷新。</p>}
          <p className="break-all text-xs text-slate-500">写入目录：{selected?.skills_path??'选择 profile 后显示'}</p>
        </>:<p className="break-all text-xs text-slate-500">{action.target.profile_name} · {action.target.install_path}（目录与身份固定）</p>}
        <label className="block text-sm">显示名称<input aria-label="显示名称" className="mt-1 w-full rounded border p-2" value={name} onChange={e=>setName(e.target.value)} maxLength={100} required /></label>
        <div className="flex justify-end gap-2"><button type="button" className={button} onClick={close}>取消</button><button type="submit" className={button} disabled={!name.trim()||(action.kind==='new'&&(!selected?.available||!!selected.existing_target_id||profilesLoading||!!profilesError))}>下一步</button></div>
      </form>
    </div>}
    {action&&confirming&&<ConfirmActionDialog title={action.kind==='delete'?'删除安装目标':'保存安装目标'} completed={blocked} busy={busy} error={actionError} onCancel={close} onConfirm={password=>void save(password)} description={<div className="space-y-2">
      {action.kind==='delete'?<><p>只移除“{action.target.name}”的安装目标配置，保留 profile 目录、Skill 源与历史。</p>{blocked&&<><p>仍有 {action.target.active_installation_count} 个已安装 Skill，请先下架。</p><button type="button" className={button} onClick={()=>{close();onBoard(action.target.id);}}>进入该目标部署看板</button></>}</>:<><p>{name} · {action.kind==='new'?profile:action.target.profile_name}</p><p className="break-all font-mono text-xs">{action.kind==='new'?selected?.skills_path:action.target.install_path}</p></>}
    </div>}/> }
  </section>;
}
