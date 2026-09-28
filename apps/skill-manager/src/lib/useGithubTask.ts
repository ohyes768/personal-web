/**
 * GitHub 后台任务轮询（design §6 / PRD R9）：扫描对话框与任务进度弹窗共用。
 *
 * - 首次查询立即发出，此后每 2s 一次；
 * - 快照进入终态（done/error）即停止轮询，终态快照保留供展示；
 * - 查询失败（404 task_not_found / 网络错误）同样停止，错误经 error 暴露；
 * - taskId 变化即重置并重启轮询，组件卸载即清理定时器；
 * - 卸载后不再写 state（PRD R9：关闭弹窗只停轮询，服务端任务继续跑完自清）。
 */
import { useEffect, useState } from 'react';
import { getGithubTask } from './api';
import type { TaskSnapshot } from './types';

export interface GithubTaskPoll {
  task: TaskSnapshot | null;
  /** 最近一次轮询失败的消息（如任务已回收/网络错误）；空串表示无失败 */
  error: string;
}

export function useGithubTask(taskId: string): GithubTaskPoll {
  const [task, setTask] = useState<TaskSnapshot | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setTask(null);
    setError('');
    if (!taskId) {
      return;
    }
    let stopped = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    function stopTimer() {
      if (timer !== undefined) {
        clearInterval(timer);
        timer = undefined;
      }
    }

    async function poll() {
      try {
        const snapshot = await getGithubTask(taskId);
        if (stopped) {
          return;
        }
        setTask(snapshot);
        if (snapshot.state !== 'running') {
          stopTimer();
        }
      } catch (err) {
        if (stopped) {
          return;
        }
        stopTimer();
        setError(err instanceof Error ? err.message : '任务查询失败');
      }
    }

    timer = setInterval(poll, 2000);
    void poll();

    return () => {
      stopped = true;
      stopTimer();
    };
  }, [taskId]);

  return { task, error };
}
