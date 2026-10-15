'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { registerGithubBatch, registerGithubSkill, startGithubScan } from '@/lib/api';
import { formatElapsed, formatProgressDetail, taskStageLabel } from '@/lib/format';
import type {
  RegisterGithubBatchInput,
  TaskSnapshot,
} from '@/lib/types';
import { useGithubTask } from '@/lib/useGithubTask';
import { repositoryKey } from '@/lib/collections';
import { dialogGhostButton, dialogPrimaryButton, errorBlockClass, solidSecondaryButton } from '@/lib/ui';
import type { SkillCard } from '@/lib/types';
import InstallDialog from './InstallDialog';
import ConfirmActionDialog from './ConfirmActionDialog';
import TaskProgressDialog from './TaskProgressDialog';

interface RegisterGithubDialogProps {
  busy: boolean;
  error?: string;
  onCancel: () => void;
  onRefresh: () => Promise<void>;
  initialRepository?: string;
  existingSkills?: SkillCard[];
}

const EMPTY_SKILLS: SkillCard[] = [];
function registeredPathsFor(skills: SkillCard[], repository: string): Set<string> {
  const key = repositoryKey(repository);
  return new Set(skills.filter(s => s.source === 'github' && key && repositoryKey(s.repository) === key).map(s => s.path));
}

/**
 * 新增 GitHub Skill 登记流程（design 5/6 + 批量登记 design §5.2）：
 * 仓库 URL → 后台扫描任务（2s 轮询，进度/已用时）→ 勾选候选目录 → 仅登记或登记并安装。勾 1 项走单条登记（手填名称/标签/简介，
 * 与改版前一致）；勾多项走批量登记（以各候选 SKILL.md 的 name 登记）。
 */
export default function RegisterGithubDialog({
  busy,
  onCancel,
  onRefresh,
  initialRepository = '',
  existingSkills = EMPTY_SKILLS,
}: RegisterGithubDialogProps) {
  const [repository, setRepository] = useState(initialRepository);
  const [scanTaskId, setScanTaskId] = useState('');
  const [scanStarting, setScanStarting] = useState(false);
  const scanRequestPending = useRef(false);
  const initializedScan = useRef('');
  const [scanSeconds, setScanSeconds] = useState(0);
  const [scanError, setScanError] = useState('');
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [summary, setSummary] = useState('');
  const [awaitPassword, setAwaitPassword] = useState(false);
  const [registerConfirm, setRegisterConfirm] = useState(false);
  const [registerBusy, setRegisterBusy] = useState(false);
  const [registerError, setRegisterError] = useState('');
  const [registerTaskId, setRegisterTaskId] = useState('');
  const registrationPending = useRef(false);

  const { task: scanTask, error: pollError } = useGithubTask(scanTaskId);
  // 只认当前 taskId 的快照：重新扫描换任务的瞬间不闪现旧结果
  const activeScan: TaskSnapshot | null =
    scanTask && scanTask.task_id === scanTaskId ? scanTask : null;
  const registeredPaths = registeredPathsFor(existingSkills, activeScan?.repository ?? repository);
  const newCandidates = activeScan?.candidates.filter(candidate => !registeredPaths.has(candidate.path)) ?? [];
  const scanning =
    scanStarting ||
    (scanTaskId !== '' &&
      !pollError &&
      (activeScan === null || activeScan.state === 'running'));

  useEffect(() => {
    if (!scanning) {
      return;
    }
    const startedAt = Date.now();
    setScanSeconds(0);
    const timer = setInterval(() => {
      setScanSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [scanning]);

  // 每轮完成时仅初始化一次，用户清空或调整后不得被轮询重新全选。
  useEffect(() => {
    if (activeScan?.state === 'done' && initializedScan.current !== activeScan.task_id) {
      initializedScan.current = activeScan.task_id;
      const registered = registeredPathsFor(existingSkills, activeScan.repository);
      setSelectedPaths(activeScan.candidates.filter(candidate => !registered.has(candidate.path)).map(candidate => candidate.path));

    }
  }, [activeScan, existingSkills]);

  async function handleScan() {
    const url = repository.trim();
    if (!url || scanning || busy || scanRequestPending.current) {
      return;
    }
    scanRequestPending.current = true;
    setScanStarting(true);
    setScanTaskId('');
    setScanError('');
    setSelectedPaths([]);
    initializedScan.current = '';
    setName('');
    setSummary('');
    setTagsText('');
    try {
      const created = await startGithubScan(url);
      setScanTaskId(created.task_id);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : '扫描失败');
    } finally {
      scanRequestPending.current = false;
      setScanStarting(false);
    }
  }

  function togglePath(path: string, checked: boolean) {
    setSelectedPaths((prev) =>
      checked ? [...prev, path] : prev.filter((p) => p !== path)
    );
  }

  // 单选时勾选的候选对象（多选为 null，表单切换为只读预填列表）
  const singleCandidate =
    selectedPaths.length === 1
      ? activeScan?.candidates.find((c) => c.path === selectedPaths[0]) ?? null
      : null;

  useEffect(() => {
    setName(singleCandidate?.name || singleCandidate?.path || '');
    setSummary(singleCandidate?.description ?? '');
    setTagsText('');
  }, [singleCandidate]);

  function handleOpenPassword(event: FormEvent) {
    event.preventDefault();
    if (
      activeScan?.state !== 'done' || selectedPaths.length === 0 ||
      (singleCandidate && !name.trim()) ||
      busy ||
      scanning
    ) {
      return;
    }
    setAwaitPassword(true);
  }

  function openRegistration() {
    if (activeScan?.state !== 'done' || !selectedPaths.length ||
      (singleCandidate && !name.trim()) || busy || scanning || registrationPending.current) return;
    setRegisterError('');
    setRegisterConfirm(true);
  }

  async function performRegistration(password: string) {
    if (registrationPending.current) return;
    registrationPending.current = true;
    setRegisterBusy(true);
    setRegisterError('');
    try {
      const batch = buildBatchInput();
      const created = singleCandidate
        ? await registerGithubSkill({ repository: batch.repository, path: selectedPaths[0],
            name: name.trim(), tags: tagsText.split(',').map(tag => tag.trim()).filter(Boolean),
            summary: summary.trim(), shared_paths: [] }, password)
        : await registerGithubBatch(batch, password);
      setRegisterTaskId(created.task_id);
      setRegisterConfirm(false);
    } catch (err) {
      setRegisterError(err instanceof Error ? err.message : '登记失败');
    } finally {
      registrationPending.current = false;
      setRegisterBusy(false);
    }
  }

  async function finishRegistration() {
    setRegisterTaskId('');
    try {
      await onRefresh();
      onCancel();
    } catch (err) {
      setRegisterError(err instanceof Error ? err.message : '刷新失败，请重新加载列表');
    }
  }

  function buildBatchInput(): RegisterGithubBatchInput {
    const candidates = activeScan?.candidates ?? [];
    return {
      repository: activeScan?.repository ?? repository.trim(),
      shared_paths: [],
      items: selectedPaths.map((path) => {
        const candidate = candidates.find((c) => c.path === path);
        return {
          path,
          name: candidate?.name || path,
          tags: [],
          summary: candidate?.description ?? '',
        };
      }),
    };
  }

  const scanFailed = activeScan?.state === 'error';
  const scanDone = activeScan?.state === 'done';
  const percent = activeScan?.progress_percent ?? null;
  const detail = activeScan ? formatProgressDetail(activeScan.progress_detail) : '';
  const allSelected =
    scanDone && selectedPaths.length === newCandidates.length;
  const dialogTitle = initialRepository ? '添加合集成员' : '新增 GitHub Skill';
  const actionDisabled = !scanDone || selectedPaths.length === 0 ||
    (singleCandidate !== null && !name.trim()) || busy || scanning || registerBusy;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={dialogTitle}
    >
      <form
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
        onSubmit={handleOpenPassword}
      >
        <h2 className="text-lg font-semibold text-slate-800">{dialogTitle}</h2>
        <p className="mt-1 text-xs text-slate-500">
          仅支持 https://github.com/&lt;owner&gt;/&lt;repo&gt;；优先使用已有缓存，首次扫描需下载仓库，登记时复用扫描结果
        </p>

        <label className="mt-3 block text-sm font-medium text-slate-700">
          仓库地址
          <div className="mt-1 flex gap-2">
            <input
              type="url"
              value={repository}
              onChange={(event) => setRepository(event.target.value)}
              placeholder="https://github.com/owner/repo"
              disabled={scanning || busy}
              className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleScan}
              disabled={!repository.trim() || scanning || busy}
              aria-busy={scanning}
              className={`flex shrink-0 items-center gap-2 ${solidSecondaryButton}`}
            >
              {scanning ? (
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white motion-reduce:animate-none"
                />
              ) : null}
              {scanStarting
                ? '准备扫描…'
                : scanning
                ? percent !== null
                  ? `${taskStageLabel(activeScan?.stage ?? '')} ${percent}%`
                  : `扫描中 ${formatElapsed(scanSeconds)}…`
                : '扫描'}
            </button>
          </div>
        </label>
        {scanning ? (
          <p className="mt-1 text-xs text-slate-500" role="status">
            {scanStarting
              ? `正在准备扫描，请稍候 · 已用时 ${formatElapsed(scanSeconds)}`
              : percent !== null
              ? `${taskStageLabel(activeScan?.stage ?? '')} ${percent}% · 已用时 ${formatElapsed(scanSeconds)}${
                  detail ? ` · ${detail}` : ''
                }`
              : `${taskStageLabel(activeScan?.stage ?? '') || '扫描中'} · 已用时 ${formatElapsed(scanSeconds)}；首次扫描可能需要几分钟`}
          </p>
        ) : null}
        {scanFailed || scanError || (!scanStarting && pollError) ? (
          <p className={`mt-2 ${errorBlockClass}`} role="alert">
            {scanFailed
              ? activeScan?.error_message ?? '扫描失败'
              : scanError || pollError}
          </p>
        ) : null}

        {scanDone ? (
          activeScan.candidates.length === 0 ? (
            <p className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-700">
              未在该仓库中找到包含 SKILL.md 的候选目录
            </p>
          ) : (
            <>
              <p className="mt-3 text-xs text-slate-500" role="status">
                扫描到 {activeScan.candidates.length} 项 · 已登记 {activeScan.candidates.length - newCandidates.length} 项 · 可添加 {newCandidates.length} 项
                {newCandidates.length === 0 ? '，当前扫描结果已全部登记' : ''}
              </p>
              <details className="mt-3">
                <summary className="cursor-pointer text-sm text-slate-700">已选择 {selectedPaths.length}/{newCandidates.length} 个可添加 Skill · 展开调整</summary>
              <fieldset className="mt-2">
                <legend className="flex w-full items-center justify-between text-sm font-medium text-slate-700">
                  候选目录（{selectedPaths.length}/{newCandidates.length}）
                  {activeScan.candidates.length > 1 ? (
                    <span className="flex gap-2 text-xs font-normal">
                      <button
                        type="button"
                        className="text-sky-600 hover:underline disabled:opacity-40"
                        disabled={allSelected || busy}
                        onClick={() =>
                          setSelectedPaths(newCandidates.map((c) => c.path))
                        }
                      >
                        全选
                      </button>
                      <button
                        type="button"
                        className="text-slate-500 hover:underline disabled:opacity-40"
                        disabled={selectedPaths.length === 0 || busy}
                        onClick={() => setSelectedPaths([])}
                      >
                        清空
                      </button>
                    </span>
                  ) : null}
                </legend>
                <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded border border-slate-200 p-2">
                  {activeScan.candidates.map((candidate) => (
                    <label
                      key={candidate.path}
                      className="flex items-start gap-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        checked={selectedPaths.includes(candidate.path)}
                        onChange={(event) =>
                          togglePath(candidate.path, event.target.checked)
                        }
                        disabled={busy || registeredPaths.has(candidate.path)}
                        className="mt-0.5"
                      />
                      <span className="min-w-0">
                        <span className="text-slate-700">
                          {candidate.name || candidate.path}
                          {registeredPaths.has(candidate.path) ? <span className="ml-2 text-xs text-slate-500">已登记</span> : null}
                        </span>
                        {candidate.name ? (
                          <span className="ml-2 text-xs text-slate-500">
                            {candidate.path}
                          </span>
                        ) : null}
                        {candidate.description ? (
                          <span
                            className="block truncate text-xs text-slate-500"
                            title={candidate.description}
                          >
                            {candidate.description}
                          </span>
                        ) : null}
                      </span>
                    </label>
                  ))}
                </div>
                {selectedPaths.length > 1 ? (
                  <p className="mt-1 text-xs text-slate-500">
                    已勾选 {selectedPaths.length} 项：将按各候选 SKILL.md
                    中的名称安装到 Hermes
                  </p>
                ) : null}
              </fieldset>
              </details>

              <details className="mt-3"><summary className="cursor-pointer text-sm text-slate-600">高级选项：名称、标签与简介</summary>
              {singleCandidate ? (
                <>
                  <label className="mt-3 block text-sm font-medium text-slate-700">
                    显示名称
                    <input
                      type="text"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      required
                      className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
                    />
                  </label>
                  <label className="mt-2 block text-sm font-medium text-slate-700">
                    标签（逗号分隔）
                    <input
                      type="text"
                      value={tagsText}
                      onChange={(event) => setTagsText(event.target.value)}
                      placeholder="research, finance"
                      className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
                    />
                  </label>
                  <label className="mt-2 block text-sm font-medium text-slate-700">
                    简介
                    <textarea
                      value={summary}
                      onChange={(event) => setSummary(event.target.value)}
                      rows={2}
                      className="mt-1 w-full rounded border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none"
                    />
                  </label>
                </>
              ) : null}
              </details>
            </>
          )
        ) : null}

        <p className="mt-4 text-xs text-slate-500">仅登记可用于管理和导出；登记并安装会同时添加到 Hermes。</p>
        {registerError && !registerConfirm ? <p role="alert" className="mt-2 text-sm text-rose-700">{registerError}</p> : null}
        <div className="mt-3 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className={dialogGhostButton}
          >
            取消
          </button>
          <button type="button" onClick={openRegistration} disabled={actionDisabled}
            className={dialogGhostButton}>
            仅登记
          </button>
          <button
            type="submit"
            disabled={actionDisabled}
            className={dialogPrimaryButton}
          >
            登记并安装到 Hermes
          </button>
        </div>
      </form>

      {registerConfirm ? <ConfirmActionDialog title="仅登记 GitHub Skill" confirmLabel="确认登记"
        description={`登记所选 ${selectedPaths.length} 个 Skill，登记后可在页面管理和导出。`}
        busy={registerBusy} error={registerError} onConfirm={performRegistration}
        onCancel={() => setRegisterConfirm(false)} /> : null}
      {registerTaskId ? <TaskProgressDialog taskId={registerTaskId} title="GitHub Skill 登记"
        onDone={finishRegistration} onClose={finishRegistration} /> : null}

      {awaitPassword ? <InstallDialog input={{scan_task_id: scanTaskId, candidates: singleCandidate ? [{path: selectedPaths[0], name: name.trim(), tags: tagsText.split(',').map(t => t.trim()).filter(Boolean), summary: summary.trim()}] : buildBatchInput().items.map(i => ({...i, tags: i.tags ?? [], summary: i.summary ?? ''}))}}
        onRefresh={onRefresh} onClose={() => { setAwaitPassword(false); onCancel(); }} /> : null}
    </div>
  );
}
