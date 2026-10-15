import { isValidElement, type ReactElement, type ReactNode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { ExportTarget, SkillCard, TargetDeployment } from '@/lib/types';

const hooks = vi.hoisted(() => ({values: [] as unknown[], index: 0}));
vi.mock('react', async original => ({...await original<typeof import('react')>(),
  useId: () => 'export-status',
  useRef: () => ({current: null}),
  useEffect: () => {},
  useState(initial: unknown) {
    const i=hooks.index++;
    if (!(i in hooks.values)) hooks.values[i]=initial;
    return [hooks.values[i], (value: unknown) => {hooks.values[i]=value;}];
  },
}));
vi.mock('react-dom', () => ({createPortal: (node: ReactNode) => node}));
import ExportStatus from './ExportStatus';

const deployment: TargetDeployment={status:'active',revision:'abcdef1234',content_hash:'hash',published_at:'2026-10-15T10:30:00+08:00',link_target:'',link_missing:false,stale:false};
const skill: SkillCard={id:'test',name:'测试 Skill',source:'local',path:'test',repository:null,tags:[],summary:'',status:'active',deployments:{hermes:deployment,claude:deployment,codex:{...deployment,stale:true}},update:null,cache_missing:false,source_missing:false};
const targets: ExportTarget[]=['claude','codex'].map(id=>({id,name:`Windows ${id}`,install_path:'',notes:'',enabled:true,deployment_count:1}));
const onExport=vi.fn();
const onDeleteExport=vi.fn();
type Props={children?:ReactNode; onClick?:()=>void; onFocus?:()=>void; onMouseEnter?:()=>void; disabled?:boolean; role?:string; 'aria-expanded'?:boolean; 'aria-label'?:string; className?:string};
function nodes(node:ReactNode):ReactElement<Props>[] {
  if(Array.isArray(node)) return node.flatMap(nodes);
  return isValidElement<Props>(node)?[node,...nodes(node.props.children)]:[];
}
function text(node:ReactNode):string {
  if(Array.isArray(node)) return node.map(text).join('');
  return isValidElement<Props>(node)?text(node.props.children):typeof node==='string'||typeof node==='number'?String(node):'';
}
function render(item=skill, configs=targets) {hooks.index=0; return ExportStatus({skill:item,targets:configs,onExport,onDeleteExport});}
function button(tree:ReactNode,label:string) {return nodes(tree).find(n=>n.type==='button'&&(text(n)===label||n.props['aria-label']===label))!;}
beforeEach(()=>{hooks.values=[]; vi.clearAllMocks(); vi.stubGlobal('document',{body:{}});});
afterEach(()=>vi.unstubAllGlobals());

it('hides when there are no active exports and excludes Hermes installation records',()=>{
  expect(render({...skill,deployments:{hermes:deployment,claude:{...deployment,status:'removed'}}})).toBeNull();
});
it('summarizes stale exports in one badge and keeps details hidden initially',()=>{
  const tree=render();
  expect(text(tree)).toBe('待更新 · 1');
  expect(nodes(tree).filter(n=>n.type==='button')).toHaveLength(1);
  expect(button(tree,'待更新 · 1').props['aria-expanded']).toBe(false);
});
it('shows a neutral count when all exports match the current source',()=>{
  const tree=render({...skill,deployments:{claude:deployment,codex:deployment}});
  expect(text(tree)).toBe('已导出 · 2');
  expect(button(tree,'已导出 · 2').props.className).toContain('text-slate-600');
});
it('shows per-target source status on keyboard focus and hover without claiming latest',()=>{
  button(render(),'待更新 · 1').props.onFocus!();
  const tree=render();
  expect(nodes(tree).some(n=>n.props.role==='tooltip')).toBe(true);
  expect(text(tree)).toContain('Windows claude');
  expect(text(tree)).toContain('与当前源一致');
  expect(text(tree)).toContain('源已更新，建议重新导出');
  expect(text(tree)).not.toContain('最新');
});
it('opens export details and routes re-export and record clearing to the right target',()=>{
  button(render(),'待更新 · 1').props.onClick!();
  const tree=render();
  expect(nodes(tree).some(n=>n.props.role==='dialog')).toBe(true);
  expect(text(tree)).toContain('abcdef1');
  expect(text(tree)).toContain('10-15');
  button(tree,'重新导出到 Windows claude').props.onClick!();
  expect(onExport).toHaveBeenCalledWith(skill,'claude');
  button(render(),'待更新 · 1').props.onClick!();
  button(render(),'清除 Windows codex 导出记录').props.onClick!();
  expect(onDeleteExport).toHaveBeenCalledWith(skill,'codex');
});
it('keeps disabled target history clearable while blocking re-export',()=>{
  button(render(skill,targets.map(t=>({...t,enabled:false}))),'待更新 · 1').props.onClick!();
  const tree=render(skill,targets.map(t=>({...t,enabled:false})));
  expect(text(tree)).toContain('已停用');
  expect(button(tree,'重新导出到 Windows claude').props.disabled).toBe(true);
  expect(button(tree,'清除 Windows claude 导出记录').props.disabled).not.toBe(true);
});
it('does not label legacy records without content hashes as matching',()=>{
  const item={...skill,deployments:{claude:{...deployment,content_hash:''}}};
  button(render(item),'已导出 · 1').props.onMouseEnter!();
  expect(text(render(item))).toContain('旧记录，无法核验');
  expect(text(render(item))).not.toContain('与当前源一致');
});
