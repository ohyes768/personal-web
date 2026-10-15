'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createInstallTarget,
  listProfileCandidates,
  removeInstallTarget,
  renameInstallTarget,
  type ProfileCandidate,
} from '@/lib/api';
import type { InstallTarget } from '@/lib/installTargets';
import {
  cardClass,
  dialogGhostButton,
  dialogPrimaryButton,
  emptyStateClass,
  errorBlockClass,
  ghostButton,
  inputClass,
  primaryButton,
} from '@/lib/ui';
import ConfirmActionDialog from './ConfirmActionDialog';
import type { Notice } from './SourceWorkspace';

type Action =
  | { kind: 'new' }
  | { kind: 'rename' | 'delete'; target: InstallTarget };
interface Props {
  active: boolean;
  targets: InstallTarget[];
  loading: boolean;
  error: string;
  onRefresh: () => Promise<void>;
  onBoard: (id: InstallTarget['id']) => void;
  onNotify?: (notice: Notice) => void;
}

export default function InstallTargetManager({
  active,
  targets,
  loading,
  error,
  onRefresh,
  onBoard,
  onNotify,
}: Props) {
  const [profiles, setProfiles] = useState<ProfileCandidate[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [profilesError, setProfilesError] = useState('');
  const [action, setAction] = useState<Action>();
  const [profile, setProfile] = useState('');
  const [name, setName] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const submitting = useRef(false);
  const loadGeneration = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const loadProfiles = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setProfilesLoading(true);
    setProfilesError('');
    try {
      const response = await listProfileCandidates();
      if (mounted.current && generation === loadGeneration.current)
        setProfiles(response.items);
    } catch (e) {
      if (mounted.current && generation === loadGeneration.current)
        setProfilesError(e instanceof Error ? e.message : '加载 profile 失败');
    } finally {
      if (mounted.current && generation === loadGeneration.current)
        setProfilesLoading(false);
    }
  }, []);
  useEffect(() => {
    if (active) void loadProfiles();
  }, [active, loadProfiles]);
  const selected = profiles.find((p) => p.profile_name === profile);
  const close = () => {
    if (!submitting.current) {
      setAction(undefined);
      setConfirming(false);
      setActionError('');
    }
  };
  const open = (next: Action) => {
    setAction(next);
    setConfirming(next.kind === 'delete');
    setName(next.kind === 'new' ? '' : next.target.name);
    setProfile('');
    setActionError('');
    if (next.kind === 'new') void loadProfiles();
  };
  const save = async (password: string) => {
    if (!action || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setActionError('');
    try {
      if (action.kind === 'new')
        await createInstallTarget(profile, name.trim(), password);
      else if (action.kind === 'rename')
        await renameInstallTarget(
          action.target.id,
          name.trim(),
          action.target.config_revision ?? 1,
          password
        );
      else
        await removeInstallTarget(
          action.target.id,
          action.target.config_revision ?? 1,
          password
        );
      if (mounted.current) {
        onNotify?.({
          kind: 'ok',
          text:
            action.kind === 'delete'
              ? `已删除安装目标「${action.target.name}」`
              : `已保存安装目标「${name.trim()}」`,
        });
        setAction(undefined);
        setConfirming(false);
        await onRefresh();
        await loadProfiles();
      }
    } catch (e) {
      if (mounted.current) {
        setActionError(e instanceof Error ? e.message : '保存失败');
        await onRefresh();
      }
    } finally {
      submitting.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const blocked =
    action?.kind === 'delete' && (action.target.active_installation_count ?? 0) > 0;
  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">安装目标</h2>
          <p className="mt-1 text-sm text-slate-500">
            默认 Skill 目录固定；这里管理各 profile 的 skills
            子目录。新增目标不会自动安装 Skill。
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className={ghostButton}
            disabled={loading || busy}
            onClick={() => void onRefresh()}
          >
            刷新
          </button>
          <button
            type="button"
            className={primaryButton}
            disabled={loading || !!error || busy}
            onClick={() => open({ kind: 'new' })}
          >
            新增 profile 目标
          </button>
        </div>
      </div>
      {error ? (
        <p
          role="alert"
          className={`flex flex-wrap items-center justify-between gap-2 ${errorBlockClass}`}
        >
          <span>{error}</span>
          <button
            type="button"
            className={ghostButton}
            onClick={() => void onRefresh()}
          >
            重试
          </button>
        </p>
      ) : null}
      {loading ? (
        <p className="p-6 text-center text-sm text-slate-500">加载目标中…</p>
      ) : !targets.length && !error ? (
        <div className={emptyStateClass}>
          <p className="text-slate-600">尚未登记 profile 目标</p>
          <p className="mt-1 text-sm text-slate-500">
            登记后即可在 Skill 卡片安装到该 profile。
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {targets.map((target) => (
            <li key={target.id} className={cardClass}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="min-w-0 break-all font-medium text-slate-800">
                      {target.name}
                    </h3>
                    {target.id === 'hermes' ? (
                      <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                        默认 · 只读
                      </span>
                    ) : null}
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${target.removed ? 'bg-slate-100 text-slate-600' : target.available ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}
                    >
                      {target.removed
                        ? '已移除'
                        : target.available
                          ? '可用'
                          : '不可用'}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    profile：{target.profile_name}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {!!target.active_installation_count && (
                    <button
                      type="button"
                      className={ghostButton}
                      onClick={() => onBoard(target.id)}
                    >
                      查看安装 / 下架
                    </button>
                  )}
                  {target.editable && (
                    <>
                      <button
                        type="button"
                        className={ghostButton}
                        disabled={busy}
                        onClick={() => open({ kind: 'rename', target })}
                      >
                        改名
                      </button>
                      <button
                        type="button"
                        className={`${ghostButton} text-rose-700`}
                        disabled={busy}
                        onClick={() => open({ kind: 'delete', target })}
                      >
                        删除目标
                      </button>
                    </>
                  )}
                </div>
              </div>
              <p className="mt-3 break-all text-sm text-slate-600">
                安装目录：
                <span className="font-mono">{target.install_path}</span>
              </p>
              <p className="mt-3 text-xs text-slate-500">
                已安装 {target.active_installation_count ?? 0} 个 Skill
              </p>
              {!target.available && target.unavailable_reason ? (
                <p className="mt-1 text-xs text-amber-700">
                  {target.unavailable_reason}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {action && action.kind !== 'delete' && !confirming && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={action.kind === 'new' ? '新增安装目标' : '修改目标名称'}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
        >
          <form
            className="max-h-[90vh] w-full max-w-lg space-y-3 overflow-y-auto rounded-lg bg-white p-5 shadow-xl"
            onSubmit={(e) => {
              e.preventDefault();
              setConfirming(true);
            }}
          >
            <h2 className="text-lg font-semibold text-slate-800">
              {action.kind === 'new' ? '新增安装目标' : '修改目标名称'}
            </h2>
            {action.kind === 'new' ? (
              <>
                {profilesLoading && (
                  <p className="text-sm text-slate-500">正在发现已有 profile…</p>
                )}
                {profilesError && (
                  <p
                    role="alert"
                    className={`flex flex-wrap items-center justify-between gap-2 ${errorBlockClass}`}
                  >
                    <span>{profilesError}</span>
                    <button
                      type="button"
                      className={ghostButton}
                      onClick={() => void loadProfiles()}
                    >
                      重试
                    </button>
                  </p>
                )}
                <label className="block text-sm text-slate-600">
                  选择已有 profile
                  <select
                    aria-label="选择已有 profile"
                    className={inputClass}
                    value={profile}
                    onChange={(e) => {
                      setProfile(e.target.value);
                      setName(e.target.value);
                    }}
                    disabled={profilesLoading || !!profilesError}
                    required
                  >
                    <option value="">请选择</option>
                    {profiles.map((p) => (
                      <option
                        key={p.profile_name}
                        value={p.profile_name}
                        disabled={!p.available || !!p.existing_target_id}
                      >
                        {p.profile_name}
                        {p.existing_target_id
                          ? '（已登记）'
                          : p.available
                            ? ''
                            : `（${p.unavailable_reason}）`}
                      </option>
                    ))}
                  </select>
                </label>
                {!profilesLoading && !profilesError && !profiles.length && (
                  <p className="text-sm text-slate-500">
                    授权目录下尚未发现 profile。请先在 Hermes 中准备环境和
                    skills 目录，再刷新。
                  </p>
                )}
                <p className="break-all text-xs text-slate-500">
                  写入目录：{selected?.skills_path ?? '选择 profile 后显示'}
                </p>
              </>
            ) : (
              <p className="break-all text-xs text-slate-500">
                {action.target.profile_name} · {action.target.install_path}
                （目录与身份固定）
              </p>
            )}
            <label className="block text-sm text-slate-600">
              显示名称
              <input
                aria-label="显示名称"
                className={inputClass}
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={100}
                required
              />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" className={dialogGhostButton} onClick={close}>
                取消
              </button>
              <button
                type="submit"
                className={dialogPrimaryButton}
                disabled={
                  !name.trim() ||
                  (action.kind === 'new' &&
                    (!selected?.available ||
                      !!selected.existing_target_id ||
                      profilesLoading ||
                      !!profilesError))
                }
              >
                下一步
              </button>
            </div>
          </form>
        </div>
      )}
      {action && confirming && (
        <ConfirmActionDialog
          title={action.kind === 'delete' ? '删除安装目标' : '保存安装目标'}
          danger={action.kind === 'delete'}
          confirmLabel={action.kind === 'delete' ? '删除' : '保存'}
          completed={blocked}
          busy={busy}
          error={actionError}
          onCancel={close}
          onConfirm={(password) => void save(password)}
          description={
            <div className="space-y-2">
              {action.kind === 'delete' ? (
                <>
                  <p>
                    只移除“{action.target.name}
                    ”的安装目标配置，保留 profile 目录、Skill 源与历史。
                  </p>
                  {blocked && (
                    <>
                      <p>
                        仍有 {action.target.active_installation_count}{' '}
                        个已安装 Skill，请先下架。
                      </p>
                      <button
                        type="button"
                        className={ghostButton}
                        onClick={() => {
                          close();
                          onBoard(action.target.id);
                        }}
                      >
                        进入该目标部署看板
                      </button>
                    </>
                  )}
                </>
              ) : (
                <>
                  <p>
                    {name} ·{' '}
                    {action.kind === 'new'
                      ? profile
                      : action.target.profile_name}
                  </p>
                  <p className="break-all font-mono text-xs">
                    {action.kind === 'new'
                      ? selected?.skills_path
                      : action.target.install_path}
                  </p>
                </>
              )}
            </div>
          }
        />
      )}
    </section>
  );
}
