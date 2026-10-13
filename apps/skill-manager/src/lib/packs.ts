import type { GithubPack } from './types';
import type { LinkTargetKey } from './targets';

export function packTargetLabel(pack: GithubPack, target: LinkTargetKey): string {
  const deployment = pack.deployments[target];
  if (deployment?.status === 'legacy_pending') return '旧安装待转换';
  if (pack.source_missing) return '源缓存缺失';
  if (deployment?.status !== 'active') return '未安装';
  if (deployment.link_missing) return '链接异常';
  return deployment.verified ? '已安装 · Agent 已验证' : '已安装 · Agent 未验证';
}
