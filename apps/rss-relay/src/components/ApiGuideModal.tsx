'use client';
import { useEffect, useState } from 'react';
import { rssRelayApi } from '@/lib/api';
import type { Channel } from '@/lib/types';
import { PUBLIC_API, feedUrl, pushExample } from '@/lib/rss-links';
import { RelayDialog } from './RelayDialog';
import { CopyText } from './CopyText';
interface Props { open: boolean; onClose: () => void; }
function Code({ text, label }: { text: string; label: string }) {
  return <div className="mt-3"><pre className="font-mono text-xs leading-relaxed bg-paper-deep border border-rule rounded-md p-4 overflow-x-auto mb-2"><code>{text}</code></pre><CopyText text={text} label={label} /></div>;
}
function Guide({ onClose }: { onClose: () => void }) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selected, setSelected] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const load = async () => {
    setLoading(true); setError('');
    try { const result = (await rssRelayApi.getChannels()).channels; setChannels(result); setSelected(result[0]?.id || ''); }
    catch (e) { setError(e instanceof Error ? e.message : '加载失败'); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);
  const json = pushExample(selected);
  const curl = [
    `curl -X POST '${PUBLIC_API}/post'`,
    `  -H 'Content-Type: application/json'`,
    `  -d '${json}'`,
  ].join(' \\\n');
  const python = `import httpx

payload = ${json}
response = httpx.post("${PUBLIC_API}/post", json=payload, timeout=10)
response.raise_for_status()
print(response.json())`;
  return <RelayDialog title="对接文档" onClose={onClose}><div className="space-y-6 leading-relaxed">
    <section><p className="text-ink-muted">先在「订阅渠道 → 管理渠道」创建渠道，再让推送工具带上它的标识。</p>
      <label className="block mt-4">选择推送渠道<select disabled={loading || !!error} value={selected} onChange={e => setSelected(e.target.value)} className="block w-full mt-2 p-2 bg-paper-deep border border-rule rounded-md">{loading ? <option>加载渠道中…</option> : channels.map(c => <option key={c.id} value={c.id}>{c.title}（{c.id}）</option>)}</select></label>
      {error && <p role="alert" className="text-danger mt-2">{error} <button onClick={load} className="underline">重试</button></p>}
    </section>
    <section><h3 className="font-serif-cn font-bold text-lg">推送接口</h3><p className="font-mono text-xs break-all mt-2">POST {PUBLIC_API}/post</p><ul className="list-disc pl-5 text-ink-muted mt-3 space-y-1"><li>title、content 必填，正文使用 Markdown。</li><li>channel 是内容渠道，例如 xinwen，决定进入哪个订阅。</li><li>source 是推送工具来源，例如 openclaw，不决定订阅归属。</li><li>url 可选，填写原文链接。省略或传 null 的 channel 归「未分类」，旧推送继续可用。</li><li>渠道标识为小写字母、数字及连字符，最多 64 位。未知渠道或非法字段返回 422，停用渠道拒绝新推送并返回 409。</li></ul>
      <p className="text-xs text-ink-muted mt-3">推送和渠道管理接口沿用当前受限网络部署环境，未单独要求 token；RSS 读取需要订阅 token。文章保留 15 天。</p>
    </section>
    {!loading && !error && selected && <><section><h3 className="font-serif-cn font-bold text-lg">推送 JSON</h3><Code text={json} label="复制 JSON" /></section><section><h3 className="font-serif-cn font-bold text-lg">curl</h3><Code text={curl} label="复制 curl" /></section><section><h3 className="font-serif-cn font-bold text-lg">Python</h3><Code text={python} label="复制 Python" /></section><section><h3 className="font-serif-cn font-bold text-lg">阅读器订阅</h3><Code text={feedUrl(selected, '<RSS_RELAY_TOKEN>')} label="复制订阅模板" /><p className="text-xs text-ink-muted mt-2">使用「订阅渠道」按钮可直接复制含实际 token 的链接。先添加各渠道订阅，再取消旧的全部订阅，避免重复。旧链接继续返回全部内容。</p></section></>}
    <section className="border-t border-rule pt-4"><h3 className="font-serif-cn font-bold text-lg">渠道维护</h3><p className="text-ink-muted mt-2">网页可新增渠道、修改名称与说明、停用或恢复；设置持久保存。改名不会改变链接，阅读器缓存名称可能需要手动刷新或改名。停用保留文章与旧链接，暂停接收新推送；「未分类」为固定系统渠道。</p></section>
  </div></RelayDialog>;
}
export default function ApiGuideModal({ open, onClose }: Props) { return open ? <Guide onClose={onClose} /> : null; }
