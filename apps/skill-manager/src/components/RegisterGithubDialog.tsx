'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { startGithubScan } from '@/lib/api';
import { formatElapsed, formatProgressDetail, taskStageLabel } from '@/lib/format';
import type {
  RegisterGithubBatchInput,
  RegisterGithubSkillInput,
  TaskSnapshot,
} from '@/lib/types';
import { useGithubTask } from '@/lib/useGithubTask';
import ConfirmActionDialog from './ConfirmActionDialog';

interface RegisterGithubDialogProps {
  busy: boolean;
  error?: string;
  onRegister: (input: RegisterGithubSkillInput, password: string) => void;
  onRegisterBatch: (input: RegisterGithubBatchInput, password: string) => void;
  onCancel: () => void;
}

/**
 * 新增 GitHub Skill 登记流程（design 5/6 + 批量登记 design §5.2）：
 * 仓库 URL → 后台扫描任务（2s 轮询，进度/已用时）→ 勾选候选目录 +
 * 随行共享资源 → 密码确认提交。勾 1 项走单条登记（手填名称/标签/简介，
 * 与改版前一致）；勾多项走批量登记（以各候选 SKILL.md 的 name 登记）。
 */
export default function RegisterGithubDialog({
  busy,
  error,
  onRegister,
  onRegisterBatch,
  onCancel,
}: RegisterGithubDialogProps) {
  const [repository, setRepository] = useState('');
  const [scanTaskId, setScanTaskId] = useState('');
  const [scanSeconds, setScanSeconds] = useState(0);
  const [scanError, setScanError] = useState('');
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [sharedPaths, setSharedPaths] = useState<string[]>([]);
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

  // 扫描完成且只有一个候选目录时自动选中（与改版前一致）
  useEffect(() => {
    if (activeScan?.state === 'done' && activeScan.candidates.length === 1) {
      const only = activeScan.candidates[0].path;
      setSelectedPaths((prev) => (prev.length > 0 ? prev : [only]));
    }
  }, [activeScan]);

  // 随行共享资源预选（design R4）：候选 SKILL.md 引用到的顶层路径，
  // 排除候选目录的祖先目录（如 codex-skills/——勾上会把整棵候选树拷进快照）
  useEffect(() => {
    if (activeScan?.state === 'done') {
      setSharedPaths(
        activeScan.referenced_paths.filter(
          (entry) =>
            !activeScan.candidates.some(
              (candidate) =>
                candidate.path === entry || candidate.path.startsWith(`${entry}/`)
            )
        )
      );
    }
  }, [activeScan]);

  async function handleScan() {
    const url = repository.trim();
    if (!url || scanning) {
      return;
    }
    setScanError('');
    setSelectedPaths([]);
    try {
      const created = await startGithubScan(url);
      setScanTaskId(created.task_id);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : '扫描失败');
    }
  }

  function togglePath(path: string, checked: boolean) {
    setSelectedPaths((prev) =>
      checked ? [...prev, path] : prev.filter((p) => p !== path)
    );
  }

  function toggleShared(path: string, checked: boolean) {
    setSharedPaths((prev) =>
      checked ? [...prev, path] : prev.filter((p) => p !== path)
    );
  }

  // 单选时勾选的候选对象（多选为 null，表单切换为只读预填列表）
  const singleCandidate =
    selectedPaths.length === 1
      ? activeScan?.candidates.find((c) => c.path === selectedPaths[0]) ?? null
      : null;

  function handleOpenPassword(event: FormEvent) {
    event.preventDefault();
    if (selectedPaths.length === 0 || (singleCandidate && !name.trim()) || busy) {
      return;
    }
    setAwaitPassword(true);
  }

  function buildInput(): RegisterGithubSkillInput {
    return {
      repository: activeScan?.repository ?? repository.trim(),
      path: selectedPaths[0],
      name: name.trim(),
      tags: tagsText
        .split(/[,,]/)
        .map((tag) => tag.trim())
        .filter(Boolean),
      summary: summary.trim(),
      shared_paths: sharedPaths,
    };
  }

  function buildBatchInput(): RegisterGithubBatchInput {
    const candidates = activeScan?.candidates ?? [];
    return {
      repository: activeScan?.repository ?? repository.trim(),
      shared_paths: sharedPaths,
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
    scanDone && selectedPaths.length === activeScan.candidates.length;

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
          仅支持 https://github.com/&lt;owner&gt;/&lt;repo&gt;；优先扫描已有缓存，无缓存时临时 clone 并查找 SKILL.md
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
                <legend className="flex w-full items-center justify-between text-sm font-medium text-slate-700">
                  候选目录（{selectedPaths.length}/{activeScan.candidates.length}）
                  {activeScan.candidates.length > 1 ? (
                    <span className="flex gap-2 text-xs font-normal">
                      <button
                        type="button"
                        className="text-sky-600 hover:underline disabled:opacity-40"
                        disabled={allSelected || busy}
                        onClick={() =>
                          setSelectedPaths(activeScan.candidates.map((c) => c.path))
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
                    <label key={candidate.path} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={selectedPaths.includes(candidate.path)}
                        onChange={(event) =>
                          togglePath(candidate.path, event.target.checked)
                        }
                        disabled={busy}
                      />
                      <span className="text-slate-700">{candidate.path}</span>
                    </label>
                  ))}
                </div>
                {selectedPaths.length > 1 ? (
                  <p className="mt-1 text-xs text-slate-400">
                    已勾选 {selectedPaths.length} 项：将按各候选 SKILL.md
                    中的名称批量登记（名称/简介可在登记后逐个补充）
                  </p>
                ) : null}
              </fieldset>

              {activeScan.top_level.length > 0 ? (
                <fieldset className="mt-3">
                  <legend className="text-sm font-medium text-slate-700">
                    随行共享资源（可选）
                  </legend>
                  <p className="mt-0.5 text-xs text-slate-400">
                    发布时一并拷入快照的仓库根级目录/文件；默认勾选候选 SKILL.md
                    中引用到的项
                  </p>
                  <div className="mt-1 max-h-32 space-y-1 overflow-y-auto rounded border border-slate-200 p-2">
                    {activeScan.top_level.map((entry) => (
                      <label key={entry.path} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={sharedPaths.includes(entry.path)}
                          onChange={(event) =>
                            toggleShared(entry.path, event.target.checked)
                          }
                          disabled={busy}
                        />
                        <span className="text-slate-700">
                          {entry.path}
                          {entry.is_dir ? '/' : ''}
                        </span>
                        {activeScan.referenced_paths.includes(entry.path) ? (
                          <span className="text-xs text-slate-400">被引用</span>
                        ) : null}
                      </label>
                    ))}
                  </div>
                </fieldset>
              ) : null}

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
            disabled={
              selectedPaths.length === 0 ||
              (singleCandidate !== null && !name.trim()) ||
              busy
            }
            className="rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700 disabled:opacity-40"
          >
            下一步：密码确认
          </button>
        </div>
      </form>

      {awaitPassword ? (
        singleCandidate ? (
          <ConfirmActionDialog
            title="确认登记 GitHub Skill"
            description={
              <p>
                将登记 {activeScan?.repository} 中的 <code>{selectedPaths[0]}</code> 为「
                {name.trim()}」，并缓存到 NAS 的 GitHub Skill 缓存目录。
                {sharedPaths.length > 0
                  ? `随行共享资源：${sharedPaths.join('、')}。`
                  : ''}
              </p>
            }
            confirmLabel="确认登记"
            busy={busy}
            error={error}
            onConfirm={(password) => onRegister(buildInput(), password)}
            onCancel={() => setAwaitPassword(false)}
          />
        ) : (
          <ConfirmActionDialog
            title={`确认批量登记 ${selectedPaths.length} 个 GitHub Skill`}
            description={
              <p>
                将登记 {activeScan?.repository} 中的 {selectedPaths.length}{' '}
                个候选目录（共享一份仓库缓存）。
                {sharedPaths.length > 0
                  ? `随行共享资源：${sharedPaths.join('、')}。`
                  : ''}
              </p>
            }
            confirmLabel="确认批量登记"
            busy={busy}
            error={error}
            onConfirm={(password) => onRegisterBatch(buildBatchInput(), password)}
            onCancel={() => setAwaitPassword(false)}
          />
        )
      ) : null}
    </div>
  );
}
