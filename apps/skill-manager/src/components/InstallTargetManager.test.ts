import {isValidElement,type ReactElement,type ReactNode} from 'react';
import {beforeEach,describe,expect,it,vi} from 'vitest';
const h=vi.hoisted(()=>({values:[] as unknown[],refs:[] as {current:unknown}[],effects:[] as {deps:unknown[];cleanup?:()=>void}[],i:0,r:0,e:0,list:vi.fn(),create:vi.fn(),rename:vi.fn(),remove:vi.fn(),refresh:vi.fn(),board:vi.fn()}));
vi.mock('react',async original=>({...await original<typeof import('react')>(),useState(initial:unknown){const i=h.i++;if(!(i in h.values))h.values[i]=typeof initial==='function'?initial():initial;return[h.values[i],(v:unknown)=>{h.values[i]=typeof v==='function'?v(h.values[i]):v;}];},useRef(initial:unknown){const i=h.r++;return h.refs[i]??(h.refs[i]={current:initial});},useCallback(fn:unknown){return fn;},useEffect(fn:()=>void|(()=>void),deps:unknown[]){const i=h.e++,old=h.effects[i]; // Callback identity is irrelevant to this controlled harness.
if(!old||(deps.length===1&&typeof deps[0]!=='function'&&deps.some((d,j)=>!Object.is(d,old.deps[j])))){old?.cleanup?.();const cleanup=fn();h.effects[i]={deps,cleanup:typeof cleanup==='function'?cleanup:undefined};}}}));
vi.mock('@/lib/api',()=>({listProfileCandidates:h.list,createInstallTarget:h.create,renameInstallTarget:h.rename,removeInstallTarget:h.remove}));
import InstallTargetManager from './InstallTargetManager';
import type {InstallTarget} from '@/lib/installTargets';
type P={children?:ReactNode;description?:ReactNode;disabled?:boolean;onClick?:()=>void;onChange?:(e:{target:{value:string}})=>void;onSubmit?:(e:{preventDefault:()=>void})=>void;onConfirm?:(p:string)=>void;completed?:boolean;error?:string;value?:string;'aria-label'?:string};
function nodes(n:ReactNode):ReactElement<P>[] {if(Array.isArray(n))return n.flatMap(nodes);if(!isValidElement<P>(n))return[];return[n,...nodes(n.props.children),...nodes(n.props.description)];}
function text(n:ReactNode):string {if(Array.isArray(n))return n.map(text).join('');if(isValidElement<P>(n))return text(n.props.children);return typeof n==='string'||typeof n==='number'?String(n):'';}
function button(n:ReactNode,label:string){const b=nodes(n).find(n=>n.type==='button'&&text(n)===label);if(!b)throw new Error(label);return b;}
const targets:InstallTarget[]=[{id:'hermes',provider:'hermes',profile_name:'default',name:'Default',install_path:'/hermes/skills',available:true,configured:true,unavailable_reason:'',editable:false},{id:'hermes:profile:one',provider:'hermes',profile_name:'one',name:'One',install_path:'/hermes/profiles/one/skills',available:true,configured:true,unavailable_reason:'',editable:true,config_revision:3,active_installation_count:0}];
const flush=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve();};
function render(list=targets){h.i=h.r=h.e=0;return InstallTargetManager({active:true,targets:list,loading:false,error:'',onRefresh:h.refresh,onBoard:h.board});}
beforeEach(()=>{h.effects.forEach(e=>e.cleanup?.());h.values=[];h.refs=[];h.effects=[];vi.clearAllMocks();h.list.mockResolvedValue({items:[{profile_name:'two',skills_path:'/hermes/profiles/two/skills',available:true,existing_target_id:null,unavailable_reason:''}]});h.refresh.mockResolvedValue(undefined);h.create.mockResolvedValue({});h.rename.mockResolvedValue({});h.remove.mockResolvedValue({});});
describe('install target manager',()=>{
 it('keeps the default readonly and creates an existing profile only after password confirmation',async()=>{
   let tree=render();await flush();
   expect(nodes(tree).filter(n=>n.type==='button'&&text(n)==='删除目标')).toHaveLength(1);
   button(tree,'新增 profile 目标').props.onClick!();await flush();tree=render();
   nodes(tree).find(n=>n.type==='select')!.props.onChange!({target:{value:'two'}});
   tree=render();nodes(tree).find(n=>n.type==='form')!.props.onSubmit!({preventDefault(){}});
   tree=render();const dialog=nodes(tree).find(n=>n.props.onConfirm)!;
   expect(text(dialog.props.description)).toContain('/hermes/profiles/two/skills');
   expect(h.create).not.toHaveBeenCalled();dialog.props.onConfirm!('password');dialog.props.onConfirm!('password');await flush();
   expect(h.create).toHaveBeenCalledExactlyOnceWith('two','two','password');expect(h.refresh).toHaveBeenCalledOnce();
 });
 it('blocks deletion with active records and opens that target board',()=>{
   let tree=render([targets[0],{...targets[1],active_installation_count:2}]);button(tree,'删除目标').props.onClick!();
   tree=render();const dialog=nodes(tree).find(n=>n.props.onConfirm)!;expect(dialog.props.completed).toBe(true);
   button(dialog,'进入该目标部署看板').props.onClick!();expect(h.board).toHaveBeenCalledWith(targets[1].id);expect(h.remove).not.toHaveBeenCalled();
 });
 it('uses the expected revision on rename and shows errors for refresh and retry',async()=>{
   let tree=render();button(tree,'改名').props.onClick!();tree=render();
   nodes(tree).find(n=>n.type==='input')!.props.onChange!({target:{value:'New name'}});tree=render();nodes(tree).find(n=>n.type==='form')!.props.onSubmit!({preventDefault(){}});
   h.rename.mockRejectedValue(new Error('目标已变化'));nodes(render()).find(n=>n.props.onConfirm)!.props.onConfirm!('password');await flush();
   expect(h.rename).toHaveBeenCalledWith(targets[1].id,'New name',3,'password');expect(nodes(render()).find(n=>n.props.onConfirm)!.props.error).toBe('目标已变化');
 });
 it('does not offer arbitrary path input when candidate discovery fails',async()=>{
   h.list.mockRejectedValue(new Error('父目录未挂载'));let tree=render();await flush();button(tree,'新增 profile 目标').props.onClick!();await flush();tree=render();
   expect(text(tree)).toContain('父目录未挂载');expect(button(tree,'下一步').props.disabled).toBe(true);
   expect(nodes(tree).filter(n=>n.type==='input')).toHaveLength(1);
 });
});
