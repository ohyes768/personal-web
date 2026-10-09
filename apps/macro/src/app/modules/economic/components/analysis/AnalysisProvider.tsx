'use client';
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeSanitize from 'rehype-sanitize';
import type { ChartContext } from '@/lib/utils/chartTheme';
import { AnalysisError, analysisRequest, streamAnalysis, type AnalysisSession, type AuthStatus, type ChartDefinition } from '@/lib/modules/analysis/api';

interface ReadingContext { chart: ChartContext; revision: string; reload: number }
interface Turn { question: string; answer: string; complete: boolean }
interface Conversation { session?: AnalysisSession; source?: ReadingContext; turns: Turn[]; busy: boolean; error?: string }
interface Bridge {
  definitions: ChartDefinition[];
  register: (context: ChartContext, revision: string) => void;
  open: (id: string, explain?: boolean) => void;
}
const Context = createContext<Bridge | null>(null);
export const useChartAnalysis = () => useContext(Context);
const emptyConversation = (): Conversation => ({ turns: [], busy: false });
function readableCitations(text: string, session?: AnalysisSession) {
  const snapshot = session?.snapshot;
  const series = snapshot ? [...snapshot.primary, ...snapshot.derived, ...snapshot.references] : [];
  return text.replace(/\[([a-z][a-z0-9_]*)\]/g, (match, id: string) => {
    const evidence = series.find(item => item.evidence_id === id);
    return evidence ? `[${evidence.label}](#evidence-${id})` : match;
  });
}
const equalContext = (a?: ReadingContext, b?: ReadingContext) => !!a && !!b && a.revision === b.revision && a.reload === b.reload && JSON.stringify(a.chart) === JSON.stringify(b.chart);

export function AnalysisProvider({ children, dataRevision = 0 }: { children: ReactNode; dataRevision?: number }) {
  const reload = useRef(dataRevision); reload.current = dataRevision;
  const [definitions, setDefinitions] = useState<ChartDefinition[]>([]);
  const readings = useRef(new Map<string, ReadingContext>());
  const [active, setActive] = useState<string | null>(null);
  const [reading, setReading] = useState<ReadingContext>();
  const activeRef = useRef(active); activeRef.current = active;
  const [conversations, setConversations] = useState<Record<string, Conversation>>({});
  const conversationsRef = useRef(conversations); conversationsRef.current = conversations;
  const [auth, setAuth] = useState<AuthStatus>();
  const [password, setPassword] = useState('');
  const [question, setQuestion] = useState('');
  const [unlocking, setUnlocking] = useState(false);
  const [authError, setAuthError] = useState('');
  const [explain, setExplain] = useState(false);
  const [autoStart, setAutoStart] = useState(false);
  const [mobile, setMobile] = useState(true);
  const jobs = useRef(new Map<string, { controller: AbortController; sessionId?: string; requestId: string }>());
  const drawer = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const definition = definitions.find(d => d.id === active);
  const conversation = active ? conversations[active] ?? emptyConversation() : emptyConversation();
  const stale = !!conversation.session && !equalContext(conversation.source, reading);

  const patch = useCallback((id: string, update: (old: Conversation) => Conversation) => {
    setConversations(old => {
      const next = { ...old, [id]: update(old[id] ?? emptyConversation()) };
      conversationsRef.current = next;
      return next;
    });
  }, []);
  const register = useCallback((chart: ChartContext, revision: string) => {
    const value = { chart, revision, reload: reload.current };
    readings.current.set(chart.chartId, value);
    if (activeRef.current === chart.chartId) setReading(old => equalContext(old, value) ? old : value);
  }, []);
  useEffect(() => {
    for (const [id, value] of readings.current) readings.current.set(id, { ...value, reload: dataRevision });
    if (activeRef.current) setReading(readings.current.get(activeRef.current));
  }, [dataRevision]);
  const open = useCallback((id: string, explanation = false) => {
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setActive(id); activeRef.current = id;
    setReading(readings.current.get(id)); setExplain(explanation); setAutoStart(!explanation); setQuestion(''); setAuthError('');
    analysisRequest<AuthStatus>('/auth').then(setAuth).catch(() => setAuthError('无法连接分析服务'));
  }, []);
  const close = useCallback(() => { setActive(null); activeRef.current = null; previousFocus.current?.focus(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    analysisRequest<{ charts: ChartDefinition[] }>('/charts', 'GET', undefined, controller.signal).then(r => setDefinitions(r.charts)).catch(() => {});
    return () => { controller.abort(); for (const job of jobs.current.values()) job.controller.abort(); };
  }, []);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)');
    const update = () => setMobile(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    if (!active || !mobile) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previous; };
  }, [active, mobile]);
  useEffect(() => {
    if (!active) return;
    drawer.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
      if (event.key === 'Tab' && drawer.current && window.matchMedia('(max-width: 1023px)').matches) {
        const items = Array.from(drawer.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), a[href]'));
        const first = items[0], last = items[items.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === drawer.current)) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || document.activeElement === drawer.current)) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => document.removeEventListener('keydown', key);
  }, [active, close]);

  const stop = async (id: string) => {
    const job = jobs.current.get(id);
    if (!job) return;
    job.controller.abort();
    if (job.sessionId) await analysisRequest(`/sessions/${job.sessionId}/requests/${job.requestId}`, 'DELETE').catch(() => {});
  };
  const run = async (message: string, fresh = false) => {
    const id = activeRef.current;
    const source = id ? readings.current.get(id) : undefined;
    if (!id || !source?.chart.dateRange || jobs.current.has(id)) return;
    const job = { controller: new AbortController(), requestId: crypto.randomUUID(), sessionId: undefined as string | undefined };
    jobs.current.set(id, job);
    patch(id, old => ({ ...(fresh ? emptyConversation() : old), busy: true, error: undefined }));
    let turnIndex = -1;
    try {
      let session = fresh ? undefined : conversationsRef.current[id]?.session;
      if (!session) {
        session = await analysisRequest<AnalysisSession>('/sessions', 'POST', {
          chart_id: id, start_date: source.chart.dateRange[0], end_date: source.chart.dateRange[1],
        }, job.controller.signal);
        if (job.controller.signal.aborted) throw new DOMException('已停止', 'AbortError');
        patch(id, old => ({ ...old, session, source }));
      }
      if (job.controller.signal.aborted) throw new DOMException('已停止', 'AbortError');
      job.sessionId = session.session_id;
      turnIndex = conversationsRef.current[id]?.turns.length ?? 0;
      patch(id, old => ({ ...old, turns: [...old.turns, { question: message, answer: '', complete: false }] }));
      await streamAnalysis(session.session_id, job.requestId, message, job.controller.signal, event => {
        if (job.controller.signal.aborted) return;
        patch(id, old => ({ ...old, turns: old.turns.map((turn, i) => i !== turnIndex ? turn : {
          ...turn, answer: event.kind === 'delta' ? turn.answer + event.text : turn.answer,
          complete: event.kind === 'done' || turn.complete,
        }) }));
      });
    } catch (error) {
      if (job.controller.signal.aborted) {
        patch(id, old => ({ ...old, error: '已停止生成，未完成回答不会进入后续对话。' }));
      } else {
        const result = job.sessionId ? await analysisRequest<{ status: string; text: string }>(`/sessions/${job.sessionId}/requests/${job.requestId}`).catch(() => null) : null;
        if (result?.status === 'complete') {
          patch(id, old => ({ ...old, turns: old.turns.map((turn, i) => i === turnIndex ? { ...turn, answer: result.text, complete: true } : turn) }));
        } else {
          patch(id, old => ({ ...old, error: error instanceof Error ? error.message : '分析失败，请重试',
            ...((error instanceof AnalysisError && error.status === 410) ? { session: undefined } : {}) }));
          if (error instanceof AnalysisError && error.status === 401) setAuth(a => a ? { ...a, unlocked: false } : a);
        }
      }
    } finally {
      jobs.current.delete(id); patch(id, old => ({ ...old, busy: false }));
    }
  };
  useEffect(() => {
    if (autoStart && active && reading?.chart.dateRange && auth?.unlocked && auth.model_ready) {
      setAutoStart(false);
      if (!conversationsRef.current[active]?.session && !jobs.current.has(active)) void run('请用大白话分析这张图的走势。', true);
    }
    // run reads captured chart/session state through refs; no re-generation on token updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, active, reading, auth]);
  const unlock = async () => {
    setUnlocking(true); setAuthError('');
    try {
      await analysisRequest('/auth/unlock', 'POST', { password });
      setPassword(''); setAuth(a => a ? { ...a, unlocked: true } : a);
    } catch (error) { setAuthError(error instanceof Error ? error.message : '解锁失败'); }
    finally { setUnlocking(false); }
  };
  const lock = async () => {
    try {
      await analysisRequest('/auth/lock', 'POST');
      for (const id of jobs.current.keys()) void stop(id);
      setAuth(a => a ? { ...a, unlocked: false } : a); setConversations({}); conversationsRef.current = {};
    } catch (error) { setAuthError(error instanceof Error ? error.message : '锁定失败'); }
  };

  return <Context.Provider value={{ definitions, register, open }}>
    <div className={active ? 'lg:pr-[440px] transition-[padding]' : ''}>{children}</div>
    {active && definition && <aside ref={drawer} tabIndex={-1} role="dialog" aria-label="图表分析助手" aria-modal={mobile || undefined}
      className="fixed inset-0 lg:left-auto lg:w-[440px] z-50 flex flex-col bg-gray-950 border-l border-gray-700 shadow-2xl outline-none">
      <header className="p-4 border-b border-gray-800 flex items-start justify-between gap-3">
        <div><h2 className="font-semibold text-gray-100">{definition.title}</h2><p className="text-xs text-gray-400 mt-1">{reading?.chart.dateRange?.join(' 至 ') ?? '暂无有效区间'}</p></div>
        <button onClick={close} className="text-gray-300 px-2" aria-label="关闭分析">✕</button>
      </header>
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm text-gray-200">
        <details open={explain} onToggle={e => setExplain(e.currentTarget.open)} className="rounded-lg border border-gray-700 p-3">
          <summary className="cursor-pointer text-sky-300">先看懂这个指标</summary><p className="mt-3 leading-7">{definition.description}</p>
        </details>
        <p className="text-xs text-gray-400">分析整张子图：{definition.series.map(series => series.label).join('、')}。图例隐藏不改变分析对象。</p>
        {authError && <p role="alert" className="text-amber-300">{authError}</p>}
        {!auth ? <p>正在检查解锁状态…</p> : !auth.configured ? <p>分析服务尚未配置密码，请联系管理员。指标说明仍可阅读。</p> : !auth.unlocked ?
          <form onSubmit={e => { e.preventDefault(); void unlock(); }} className="rounded-xl border border-gray-700 p-4 space-y-3">
            <label className="block" htmlFor="analysis-password">输入密码解锁分析</label>
            <input id="analysis-password" type="password" autoComplete="current-password" maxLength={200} value={password} onChange={e => setPassword(e.target.value)} className="w-full rounded bg-gray-900 border border-gray-600 p-2" />
            <p className="text-xs text-gray-400">同一浏览器7天免重复输入。刷新后聊天清空，解锁保留。</p>
            <button disabled={unlocking || !password} className="rounded bg-sky-700 px-4 py-2 disabled:opacity-40">{unlocking ? '正在解锁…' : '解锁'}</button>
          </form> : <>
          <div className="flex items-center justify-between"><span className="text-xs text-emerald-300">已解锁 · DeepSeek</span><button onClick={() => void lock()} className="text-xs text-gray-400 underline">锁定分析</button></div>
          {!auth.model_ready && <p className="text-amber-300">DeepSeek密钥尚未配置，暂时无法分析。</p>}
          {conversation.session && <div className="rounded bg-gray-900 p-3 text-xs text-gray-400 space-y-2">
            <p>当前回答依据：{conversation.session.snapshot.range.join(' 至 ')} · {conversation.session.snapshot.quality === 'ok' ? '数据可用' : '部分数据不足'}</p>
            {[...conversation.session.snapshot.primary, ...conversation.session.snapshot.derived, ...conversation.session.snapshot.references].map(series => <p key={series.evidence_id} id={`evidence-${series.evidence_id}`}>
              {series.label}：{series.statistics ? `${series.statistics.end.value.toFixed(3)}${series.unit}（${series.statistics.end.date}，${series.statistics.count}个观测）` : '缺失'}
            </p>)}
          </div>}
          {stale && <p className="rounded bg-amber-950 p-3 text-amber-200">图表范围或数据已变化。当前对话仍使用上面的旧快照，点击“按当前范围重新分析”更新。</p>}
          {conversation.turns.map((turn, i) => <div key={i} className="space-y-3">
            <p className="rounded-lg bg-sky-950 px-3 py-2 text-sky-100">{turn.question}</p>
            <div className="prose prose-invert prose-sm max-w-none leading-7 break-words"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>{turn.answer ? readableCitations(turn.answer, conversation.session) : conversation.busy && i === conversation.turns.length - 1 ? '正在分析…' : '回答未完成'}</ReactMarkdown></div>
            {!turn.complete && turn.answer && <p className="text-xs text-gray-500">{conversation.busy && i === conversation.turns.length - 1 ? '生成中…' : '未完成，未加入后续对话'}</p>}
          </div>)}
          {conversation.error && <p role="alert" className="text-amber-300">{conversation.error}</p>}
          <div className="flex gap-2 flex-wrap">
            {conversation.busy ? <button onClick={() => void stop(active)} className="rounded border border-gray-500 px-3 py-2">停止生成</button> :
              <button disabled={!reading?.chart.dateRange || !auth.model_ready} onClick={() => void run('请用大白话分析这张图的走势。', true)} className="rounded bg-sky-700 px-3 py-2 disabled:opacity-40">{conversation.session ? '按当前范围重新分析' : '分析当前走势'}</button>}
            {conversation.error && !conversation.busy && <button disabled={!auth.model_ready} onClick={() => void run(conversation.turns.at(-1)?.question ?? '请用大白话分析这张图的走势。', !conversation.session)} className="rounded border border-gray-500 px-3 py-2">重试</button>}
          </div>
          {conversation.session && <div className="flex gap-2 flex-wrap">{['讲简单点', '只解释利差', '结合DR007看看'].map(text => <button key={text} disabled={conversation.busy} onClick={() => void run(text)} className="text-xs rounded-full border border-gray-700 px-3 py-2 disabled:opacity-40">{text}</button>)}</div>}
        </>}
      </div>
      {auth?.unlocked && <form onSubmit={e => { e.preventDefault(); const text = question.trim(); if (text) { setQuestion(''); void run(text); } }} className="p-4 border-t border-gray-800 flex gap-2">
        <label htmlFor="analysis-question" className="sr-only">继续追问</label>
        <textarea id="analysis-question" rows={2} maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} placeholder="继续问，比如：利差扩大是什么意思？" disabled={conversation.busy || !conversation.session} className="flex-1 min-w-0 bg-gray-900 rounded p-2 text-sm disabled:opacity-40" />
        <button disabled={conversation.busy || !conversation.session || !question.trim()} className="rounded bg-sky-700 px-3 disabled:opacity-40">发送</button>
      </form>}
    </aside>}
  </Context.Provider>;
}
