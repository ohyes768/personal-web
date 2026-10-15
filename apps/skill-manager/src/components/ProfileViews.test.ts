import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import SourceWorkspace from './SourceWorkspace';
import DeployBoard from './DeployBoard';
import { InstallTargetsContext, type InstallTarget } from '@/lib/installTargets';
import type { SkillCard } from '@/lib/types';

const named = 'hermes:profile:ohyes768' as const;
const targets: InstallTarget[] = ['hermes', named].map(id => ({id:id as InstallTarget['id'],provider:'hermes',name:id,profile_name:id,install_path:`/targets/${id}`,available:true,configured:true,unavailable_reason:''}));
const skill: SkillCard = {id:'alpha',name:'Alpha',source:'local',path:'alpha',repository:null,tags:[],summary:'',status:'active',update:null,cache_missing:false,source_missing:false,deployments:{hermes:{status:'active',revision:'v1',published_at:'now',link_target:'/source/alpha',link_missing:false,stale:false,content_hash:''}}};
const workspaceProps = {source:'local' as const,skills:[skill],loading:false,exportTargets:[],targetsError:'',onManageTargets:vi.fn(),onRefresh:vi.fn(),onNotify:vi.fn(),onClone:vi.fn(),onDelete:vi.fn(),onUnpublish:vi.fn(),onUnpublishCollection:vi.fn()};
function render(current: InstallTarget['id'], content: ReturnType<typeof createElement>, error='') {
  return renderToStaticMarkup(createElement(InstallTargetsContext.Provider,{value:{current,targets,error,loading:false}},content));
}
describe('current profile views', () => {
  it('shows the same Skill installed only in its current profile and hides self-source updates', () => {
    const normal = render('hermes',createElement(SourceWorkspace,workspaceProps));
    expect(normal).toContain('已安装');
    expect(normal).not.toContain('aria-label="安装 Alpha"');
    const other = render(named,createElement(SourceWorkspace,workspaceProps));
    expect(other).toContain('未安装');
    expect(other).toContain('aria-label="安装 Alpha"');
  });
  it('scopes board installations to the selected profile', () => {
    const board = (agent: InstallTarget['id']) => createElement(DeployBoard,{skills:[skill],agent,onAgentChange:vi.fn(),onUnpublish:vi.fn(),onUnpublishCollection:vi.fn()});
    expect(render('hermes',board('hermes'))).toContain('Alpha');
    expect(render(named,board(named))).not.toContain('Alpha');
  });
  it('disables installation when target metadata failed to load', () => {
    const markup = render(named,createElement(SourceWorkspace,workspaceProps),'load failed');
    expect(markup).not.toMatch(/aria-label="导出 Skill"[^>]*disabled=""/);
    expect(markup).toMatch(/disabled=""[^>]*aria-label="安装 Alpha"|aria-label="安装 Alpha"[^>]*disabled=""/);
  });
});
