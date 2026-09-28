'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { startGithubScan } from '@/lib/api';
import { formatElapsed, formatProgressDetail, taskStageLabel } from '@/lib/format';
import type { RegisterGithubSkillInput, TaskSnapshot } from '@/lib/types';
import { useGithubTask } from '@/lib/useGithubTask';
import ConfirmActionDialog from './ConfirmActionDialog';

interface RegisterGithubDialogProps {
  busy: boolean;
  error?: string;
  onRegister: (input: RegisterGithubSkillInput, password: string) => void;
  onCancel: () => void;
}

/**
 * 新增 GitHub Skill 登记流程（design 5/6）：
 * 仓库 URL → 后台扫描任务（2s 轮询，进度/已用时）→ 选择目录 + 名称/标签
 * → 密码确认提交（登记本体也是后台任务，进度由 TaskProgressDialog 接管）。
 */
export default function RegisterGithubDialog({
  busy,
  error,
  onRegister,
  onCancel,
}: RegisterGithubDialogProps) {
  const [repository, setRepository] = useState('');
  const [scanTaskId, setScanTaskId] = useState('');
  const [scanSeconds, setScanSeconds] = useState(0);
  const [scanError, setScanError] = useState('');
  const [selectedPath, setSelectedPath] = useState('');
  const [name, setName] = useState('');
  const [tagsText, setTagsText] = useState('');
  const [summary, setSummary] = useState('');
  const [awaitPassword, setAwaitPassword] = useState(false);

  const { task: scanTask, error: pollError } = useGithubTask(scanTaskId);
  // 只认当前 taskId 的快照：重新扫描换任务的瞬间不闪现旧结果
  const activeScan: TaskSnapshot | null =
    scanTask && scanTask.task_id === scanTaskId ? scanTask : null;
  const scanning =
    scanTaskId !== '' && (activeScan === null || activeScan.state === 'running');

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

  // 扫描完成且只有一个候选目录时自动选中
  useEffect(() => {
    if (activeScan?.state === 'done' && activeScan.candidates.length === 1) {
      setSelectedPath((prev) => prev || activeScan.candidates[0]);
    }
  }, [activeScan]);

  async function handleScan() {
    const url = repository.trim();
    if (!url || scanning) {
      return;
    }
    setScanError('');
    setSelectedPath('');
    try {
      const created = await startGithubScan(url);
      setScanTaskId(created.task_id);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : '扫描失败');
    }
  }

  function handleOpenPassword(event: FormEvent) {
    event.preventDefault();
    if (!selectedPath || !name.trim() || busy) {
      return;
    }
    setAwaitPassword(true);
  }

  function buildInput(): RegisterGithubSkillInput {
    return {
      repository: activeScan?.repository ?? repository.trim(),
      path: selectedPath,
      name: name.trim(),
      tags: tagsText
        .split(/[,,]/)
        .map((tag) => tag.trim())
        .filter(Boolean),
      summary: summary.trim(),
    };
  }

  const scanFailed = activeScan?.state === 'error';
  const scanDone = activeScan?.state === 'done';
  const percent = activeScan?.progress_percent ?? null;
  const detail = activeScan ? formatProgressDetail(activeScan.progress_detail) : '';

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="新增 GitHub Skill"
    >
      <form
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
        onSubmit={handleOpenPassword}
      >
        <h2 className="text-lg font-semibold text-slate-800">新增 GitHub Skill</h2>
        <p className="mt-1 text-xs text-slate-400">
          仅支持 https://github.com/&lt;owner&gt;/&lt;repo&gt;；扫描会临时 clone 仓库并查找 SKILL.md
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
              className="shrink-0 rounded bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-800 disabled:opacity-40"
            >
              {scanning
                ? percent !== null
                  ? `${taskStageLabel(activeScan?.stage ?? '')} ${percent}%`
                  : `扫描中 ${formatElapsed(scanSeconds)}…`
                : '扫描'}
            </button>
          </div>
        </label>
        {scanning ? (
          <p className="mt-1 text-xs text-slate-400">
            {percent !== null
              ? `${taskStageLabel(activeScan?.stage ?? '')} ${percent}%${
                  detail ? ` · ${detail}` : ''
                }`
              : '扫描会临时克隆整个仓库；大仓库在慢速网络下可能需要几分钟'}
          </p>
        ) : null}
        {scanFailed || scanError || pollError ? (
          <p className="mt-2 rounded bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
            {scanFailed
              ? activeScan?.error_message ?? '扫描失败'
              : scanError || pollError}
          </p>
        ) : null}

        {scanDone ? (
          activeScan.candidates.length === 0 ? (
            <p className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-700">
              未在该仓库中找到包含 SKILL.md 的候选目录
            </p>
          ) : (
            <>
              <fieldset className="mt-3">
                <legend className="text-sm font-medium text-slate-700">
                  候选目录（{activeScan.candidates.length}）
                </legend>
                <div className="mt-1 max-h-40 space-y-1 overflow-y-auto rounded border border-slate-200 p-2">
                  {activeScan.candidates.map((path) => (
                    <label key={path} className="flex items-center gap-2 text-sm">
                      <input
                        type="radio"
                        name="candidate"
                        value={path}
                        checked={selectedPath === path}
                        onChange={() => setSelectedPath(path)}
                      />
                      <span className="text-slate-700">{path}</span>
                    </label>
                  ))}
                </div>
              </fieldset>

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
          )
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={!selectedPath || !name.trim() || busy}
            className="rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700 disabled:opacity-40"
          >
            下一步：密码确认
          </button>
        </div>
      </form>

      {awaitPassword ? (
        <ConfirmActionDialog
          title="确认登记 GitHub Skill"
          description={
            <p>
              将登记 {activeScan?.repository} 中的 <code>{selectedPath}</code> 为「
              {name.trim()}」，并缓存到 NAS 的 GitHub Skill 缓存目录。
            </p>
          }
          confirmLabel="确认登记"
          busy={busy}
          error={error}
          onConfirm={(password) => onRegister(buildInput(), password)}
          onCancel={() => setAwaitPassword(false)}
        />
      ) : null}
    </div>
  );
}
