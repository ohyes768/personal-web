'use client';

import { useEffect, useRef, useState } from 'react';
import { formatElapsed, formatProgressDetail, taskStageLabel } from '@/lib/format';
import type { RegisterBatchResultItem, TaskSnapshot } from '@/lib/types';
import { useGithubTask } from '@/lib/useGithubTask';

interface TaskProgressDialogProps {
  taskId: string;
  title: string;
  /** 快照 state=done 时回调一次（关框 + 刷新列表 + notice 由调用方处理）。
   * 批量登记任务（results 非空）done 后弹窗停留展示逐项结果，由「完成」
   * 按钮触发本回调并携带终态快照 */
  onDone: (task: TaskSnapshot) => void;
  /** 运行中提前关闭（服务端任务继续执行）或失败后关闭 */
  onClose: () => void;
}

function ResultsList({ results }: { results: RegisterBatchResultItem[] }) {
  return (
    <ul className="mt-2 space-y-1 rounded bg-slate-50 px-3 py-2 text-sm">
      {results.map((item) => (
        <li key={item.skill_id} className="flex items-baseline justify-between gap-2">
          <span className="text-slate-700">{item.skill_id}</span>
          <span
            className={
              item.status === 'success' ? 'text-emerald-600' : 'text-rose-600'
            }
          >
            {item.status === 'success' ? '成功' : item.error || '失败'}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * GitHub 后台任务进度弹窗（design §6 / PRD R9）：
 * 登记 / Clone / 批量登记密码确认后接管进度展示。有百分比显示「阶段 N% ·
 * 速度」，无进度退回已用时计时；失败展示后端 message + 关闭按钮（批量任务
 * 同时展示逐项结果）；done 触发 onDone——批量任务停留展示逐项成败清单。
 */
export default function TaskProgressDialog({
  taskId,
  title,
  onDone,
  onClose,
}: TaskProgressDialogProps) {
  const { task, error } = useGithubTask(taskId);
  const [seconds, setSeconds] = useState(0);
  const doneFired = useRef(false);

  const taskFailed = task?.state === 'error';
  const failed = taskFailed || error !== '';
  const running = !failed && (task === null || task.state === 'running');
  const batchResults = task?.results ?? [];
  const doneWithResults = task?.state === 'done' && batchResults.length > 0;

  useEffect(() => {
    if (!running) {
      return;
    }
    const startedAt = Date.now();
    setSeconds(0);
    const timer = setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [running]);

  // 无逐项结果的 done（登记/Clone 单任务）自动收尾；批量任务走「完成」按钮
  useEffect(() => {
    if (task?.state === 'done' && task.results.length === 0 && !doneFired.current) {
      doneFired.current = true;
      onDone(task);
    }
  }, [task, onDone]);

  const stageText = task ? taskStageLabel(task.stage) : '正在连接任务';
  const percent = task?.progress_percent ?? null;
  const detail = task ? formatProgressDetail(task.progress_detail) : '';
  const failText = taskFailed ? (task?.error_message ?? '任务失败') : error;
  const succeeded = batchResults.filter((item) => item.status === 'success').length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 className="text-lg font-semibold text-slate-800">{title}</h2>

        {running ? (
          <>
            <p className="mt-3 text-sm text-slate-600">
              {percent !== null ? `${stageText} ${percent}%` : `${stageText}…`}
              {percent !== null && detail ? ` · ${detail}` : ''}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              已用时 {formatElapsed(seconds)}；关闭窗口不会中断后台任务
            </p>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                后台运行
              </button>
            </div>
          </>
        ) : null}

        {doneWithResults ? (
          <>
            <p className="mt-3 text-sm text-slate-600">
              批量登记完成：{succeeded}/{batchResults.length} 项成功
            </p>
            <ResultsList results={batchResults} />
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => onDone(task)}
                className="rounded bg-sky-600 px-4 py-2 text-sm text-white hover:bg-sky-700"
              >
                完成
              </button>
            </div>
          </>
        ) : null}

        {failed ? (
          <>
            <p className="mt-3 rounded bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
              {failText}
            </p>
            {batchResults.length > 0 ? <ResultsList results={batchResults} /> : null}
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                关闭
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
