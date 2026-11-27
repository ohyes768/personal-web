"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ApiError,
  type ServiceListItem,
  type SummaryResponse,
} from "@/lib/api";
import { describeJob, waitForJob } from "@/lib/jobs";
import { matchesTags } from "@/lib/tagFilter";
import {
  formatRelative,
  HEALTH,
  RUNTIME,
  tlsErrorHint,
  tlsInvalidReason,
  tlsTone,
} from "@/lib/status";
import { DockerNotice } from "@/components/DockerNotice";
import { SafeLink, Spinner, StateBadge, Toast } from "@/components/Widgets";
import { TagBadge } from "@/components/TagBadge";
import { ServiceInfoEditor } from "@/components/ServiceInfoEditor";
import { TagEditor } from "@/components/TagEditor";
import { TagFilterBar } from "@/components/TagFilterBar";

export default function HomePage() {
  return <ServiceList />;
}

function ServiceList() {
  const [items, setItems] = useState<ServiceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [query, setQuery] = useState("");
  // 标签筛选（多选 AND）与标签编辑弹窗
  const [tagFilter, setTagFilter] = useState<string[]>([]);
  const [editingTags, setEditingTags] = useState<ServiceListItem | null>(null);
  const [savingTags, setSavingTags] = useState(false);
  // 编辑弹窗：名称 + 用途（+ 尚未登记时的主入口 URL）
  const [editingInfo, setEditingInfo] = useState<ServiceListItem | null>(null);
  const [savingInfo, setSavingInfo] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [toastKind, setToastKind] = useState<"ok" | "error">("ok");
  function notify(message: string, kind: "ok" | "error" = "ok") {
    setToastKind(kind);
    setToast(message);
  }
  // 刷新任务在后台跑，按钮各自转圈；两类任务互不阻塞。
  const [pending, setPending] = useState<{ docker: boolean }>({ docker: false });
  const aborters = useRef<Set<AbortController>>(new Set());
  // 同一类任务的防重入（state 更新要等一次渲染，用 ref 才能挡住连点）
  const inFlight = useRef<Set<"docker">>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, totals] = await Promise.all([
        api.listServices({ query, page: 1, page_size: 100 }),
        api.summary(),
      ]);
      setItems(list.items);
      setTotal(list.total);
      setSummary(totals);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  // 离开页面时停掉还在轮询的刷新任务，别让后台继续空转
  useEffect(() => {
    const controllers = aborters.current;
    return () => {
      controllers.forEach((controller) => controller.abort());
      controllers.clear();
    };
  }, []);

  // 从详情页点标签跳回来时带上 ?tag=xxx：初次进入按这个标签筛。
  // 用 window.location 读而不是 useSearchParams——后者在静态页要挂 Suspense 边界。
  useEffect(() => {
    const tag = new URLSearchParams(window.location.search).get("tag");
    if (tag) setTagFilter([tag]);
  }, []);

  // 候选标签：后端给的全库词表（不随搜索/分组缩小，筛选栏才选得到别的标签）
  const allTags = useMemo(() => summary?.all_tags ?? [], [summary]);

  // 筛选链：搜索（后端）→ 标签（前端，多选 AND）。列表平铺，不分组。
  const tabItems = useMemo(
    () => items.filter((item) => matchesTags(item.tags, tagFilter)),
    [items, tagFilter],
  );

  async function saveTags(tags: string[]) {
    if (!editingTags) return;
    setSavingTags(true);
    try {
      const updated = await api.patchService(editingTags.id, {
        tags,
        revision: editingTags.revision,
      });
      // 就地更新：revision 必须跟着后端返回的走，否则下一次 PATCH 会 409
      setItems((prev) =>
        prev.map((item) =>
          item.id === updated.id
            ? { ...item, tags: updated.tags, revision: updated.revision }
            : item,
        ),
      );
      // 词表也要跟上：新建的标签立刻能出现在筛选栏里
      setSummary((prev) =>
        prev
          ? {
              ...prev,
              all_tags: Array.from(new Set([...prev.all_tags, ...updated.tags])).sort(),
            }
          : prev,
      );
      setEditingTags(null);
      notify("标签已保存");
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "保存标签失败", "error");
    } finally {
      setSavingTags(false);
    }
  }

  function startEditInfo(item: ServiceListItem) {
    setEditingInfo(item);
  }

  function cancelEditInfo() {
    setEditingInfo(null);
  }

  async function saveInfo(values: {
    name: string;
    description: string;
    url: string | null;
    repo: { owner: string; repo: string } | null;
    installedTagNote: string;
  }) {
    if (!editingInfo) return;
    setSavingInfo(true);
    try {
      const updated = await api.patchService(editingInfo.id, {
        name: values.name,
        description: values.description,
        revision: editingInfo.revision,
      });
      // 就地更新：revision 用后端返回值覆盖，否则下一次 PATCH 会 409
      setItems((prev) =>
        prev.map((item) =>
          item.id === updated.id
            ? {
                ...item,
                name: updated.name,
                description: updated.description,
                revision: updated.revision,
              }
            : item,
        ),
      );
      // 还没登记过主入口的话，这次顺手登记一个（填了就纳入 URL / 证书检查）
      if (values.url) {
        await api.upsertPrimaryEndpoint(editingInfo.id, values.url);
      }
      // 源码仓库：填了就登记（含当前版本备注），清空就解绑
      const previous = editingInfo.status.release_info;
      let repoChanged = false;
      if (values.repo) {
        const same =
          previous &&
          previous.owner === values.repo.owner &&
          previous.repo === values.repo.repo &&
          previous.installed_tag_note === values.installedTagNote;
        if (!same) {
          await api.setReleaseSource(editingInfo.id, {
            owner: values.repo.owner,
            repo: values.repo.repo,
            installed_tag_note: values.installedTagNote,
          });
          repoChanged = true;
        }
      } else if (previous) {
        await api.deleteReleaseSource(editingInfo.id);
        repoChanged = true;
      }
      cancelEditInfo();
      notify(values.url ? "已保存，主入口已登记" : "已保存");
      await load();
      if (values.url) {
        // 触发一次该服务的证书检查，别让用户干等下一轮定时
        try {
          await api.refresh("tls", editingInfo.id);
        } catch {
          // 检查提交失败不影响保存结果
        }
      }
      if (repoChanged) {
        // 仓库刚登记/解绑：立即跑一次 release 检查，版本列马上有数
        try {
          await api.refresh("releases", editingInfo.id);
        } catch {
          // 检查提交失败不影响保存结果
        }
      }
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "保存失败", "error");
    } finally {
      setSavingInfo(false);
    }
  }

  async function removeService(item: ServiceListItem) {
    if (
      !window.confirm(
        `从台账移除「${item.name}」？只删除本应用的记录与关联，运行中的容器不受影响。`,
      )
    ) {
      return;
    }
    try {
      await api.deleteService(item.id);
      notify("已移除");
      await load();
    } catch (caught) {
      notify(caught instanceof ApiError ? caught.message : "移除失败", "error");
    }
  }

  async function refresh(kind: "docker") {
    if (inFlight.current.has(kind)) return;
    const label = "容器扫描";
    inFlight.current.add(kind);
    setPending((prev) => ({ ...prev, [kind]: true }));
    const controller = new AbortController();
    aborters.current.add(controller);
    try {
      const job = await api.refresh(kind);
      if (controller.signal.aborted) return;
      notify(
        job.deduplicated
          ? "已有同类型任务在跑，复用现有任务"
          : `已提交${label}任务`,
      );
      // 任务在后台跑，轮询到终态再刷新列表——固定等 3 秒会漏掉慢任务的结果。
      const result = await waitForJob(job.id, { signal: controller.signal });
      if (result.aborted) return;
      if (result.timedOut) {
        notify(`${label}还没跑完，仍在后台执行，稍后再看`);
      } else if (result.job) {
        const failed =
          result.job.state === "failed" ||
          result.job.state === "partial_failed" ||
          result.job.state === "interrupted";
        notify(describeJob(label, result.job), failed ? "error" : "ok");
      }
      await load();
    } catch (caught) {
      if (!controller.signal.aborted) {
        notify(caught instanceof ApiError ? caught.message : `${label}失败`, "error");
      }
    } finally {
      aborters.current.delete(controller);
      inFlight.current.delete(kind);
      setPending((prev) => ({ ...prev, [kind]: false }));
    }
  }

  return (
    <>
      <h1>服务</h1>
      <p className="lead">台账与运行状态。</p>

      {summary ? (
        <div className="kpi-row">
          <div className="kpi">
            <div className="num">{summary.services}</div>
            <div className="lbl">业务服务</div>
          </div>
          <div className="kpi">
            <div className="num">{summary.docker_components}</div>
            <div className="lbl">发现容器</div>
          </div>
          <div className="kpi">
            <div className="num">{summary.components}</div>
            <div className="lbl">已关联组件</div>
          </div>
          <Link className="kpi kpi-link" href="/discovery?bound=unbound">
            <div
              className="num"
              style={{
                color:
                  summary.unregistered_components - summary.ignored_components > 0
                    ? "var(--warn)"
                    : undefined,
              }}
            >
              {summary.unregistered_components - summary.ignored_components}
            </div>
            <div className="lbl">未入账 · 不含已忽略 →</div>
          </Link>
        </div>
      ) : null}

      {summary && !summary.docker_available ? (
        <DockerNotice error={summary.docker_error} />
      ) : null}

      <div className="card tight">
        <div className="btn-row">
          <input
            type="search"
            placeholder="搜索名称 / 用途 / 标签 / 域名 / 端口 / 路径"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="搜索服务"
            className="toolbar-search"
          />
          <div className="scan-group">
            <button
              className="btn"
              type="button"
              disabled={pending.docker}
              aria-busy={pending.docker}
              onClick={() => void refresh("docker")}
            >
              {pending.docker ? (
                <>
                  <Spinner />
                  扫描中…
                </>
              ) : (
                "扫描容器"
              )}
            </button>
            {summary?.docker_last_success_at ? (
              <span className="scan-caption">
                上次扫描 {formatRelative(summary.docker_last_success_at)}
              </span>
            ) : null}
          </div>
        </div>

        <TagFilterBar allTags={allTags} selected={tagFilter} onChange={setTagFilter} />
      </div>

      {error ? <p className="notice bad">{error}</p> : null}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : tabItems.length === 0 ? (
        <div className="card">
          <p>
            {items.length === 0
              ? "台账还是空的。到「容器管理」从运行中的容器建立台账条目。"
              : tagFilter.length > 0
                ? `没有同时具备这些标签的服务（${tagFilter.join("、")}）。`
                : "没有匹配的服务。"}
          </p>
          <div className="btn-row">
            {tagFilter.length > 0 ? (
              <button className="btn" type="button" onClick={() => setTagFilter([])}>
                清除标签筛选
              </button>
            ) : null}
            <Link className="btn" href="/discovery">
              去容器管理
            </Link>
          </div>
        </div>
      ) : (
        <div className="table-scroll">
          <table className="cols-fit">
            <thead>
              <tr>
                <th className="mcol-service">服务</th>
                <th className="mcol-entry">主入口</th>
                <th className="mcol-port">端口</th>
                <th className="mcol-run">运行</th>
                <th className="mcol-health">健康</th>
                <th className="mcol-cert">证书</th>
                <th className="mcol-ver">版本</th>
                <th className="mcol-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {tabItems.map((item) => (
                <tr
                  key={item.id}
                  data-service-id={item.id}
                  className={
                    item.primary_endpoint?.tls_check_status === "error"
                      ? "row-anomaly"
                      : undefined
                  }
                >
                  <td>
                    <span className="service-name">{item.name}</span>
                    {item.description ? (
                      <div className="small truncate">{item.description}</div>
                    ) : null}
                    <div className="tag-row" style={{ marginTop: 2 }}>
                      {item.tags.map((tag) => (
                        <TagBadge key={tag} tag={tag} active={tagFilter.includes(tag)} />
                      ))}
                      <button
                        type="button"
                        className="tag-add"
                        onClick={() => setEditingTags(item)}
                        aria-label={`编辑 ${item.name} 的标签`}
                      >
                        ＋标签
                      </button>
                      {item.status.release_info ? (
                        <SafeLink
                          href={`https://github.com/${item.status.release_info.owner}/${item.status.release_info.repo}`}
                          className="btn btn-mini"
                        >
                          源码
                        </SafeLink>
                      ) : null}
                    </div>
                  </td>
                  <td>
                    {item.primary_endpoint ? (
                      <SafeLink
                        href={item.primary_endpoint.url}
                        className="mono entry-url"
                        title={item.primary_endpoint.url}
                      >
                        {item.primary_endpoint.url}
                      </SafeLink>
                    ) : (
                      <span className="muted small">无对外入口</span>
                    )}
                  </td>
                  <td className="mono">
                    {item.primary_endpoint?.server_port ?? "—"}
                  </td>
                  <td>
                    <StateBadge tone={RUNTIME[item.status.runtime]} />
                    <div className="small muted">{item.component_count} 个组件</div>
                  </td>
                  <td>
                    <StateBadge tone={HEALTH[item.status.health]} />
                  </td>
                  <td>
                    {item.primary_endpoint?.tls_check ? (
                      item.primary_endpoint.tls_check_status === "error" ? (
                        <>
                          <StateBadge tone={{ tone: "warn", label: "检查失败" }} />
                          {item.primary_endpoint.tls_check_error ? (
                            <div
                              className="small muted truncate"
                              title={item.primary_endpoint.tls_check_error}
                            >
                              {item.primary_endpoint.tls_check_error}
                            </div>
                          ) : null}
                          {tlsErrorHint(item.primary_endpoint.tls_check_error) ? (
                            <div className="small" style={{ color: "var(--muted)" }}>
                              {tlsErrorHint(item.primary_endpoint.tls_check_error)}
                            </div>
                          ) : null}
                        </>
                      ) : item.primary_endpoint.tls_check_status === "success" ? (
                        <>
                          <StateBadge
                            tone={tlsTone(
                              (item.primary_endpoint.tls_state ?? "unknown") as never,
                              item.primary_endpoint.tls_invalid_reason,
                            )}
                          />
                          {item.primary_endpoint.tls_days_remaining !== null &&
                          item.primary_endpoint.tls_days_remaining >= 0 ? (
                            <div className="small muted">
                              {item.primary_endpoint.tls_days_remaining} 天
                            </div>
                          ) : null}
                          {item.primary_endpoint.tls_days_remaining !== null &&
                          item.primary_endpoint.tls_days_remaining < 0 &&
                          item.primary_endpoint.tls_not_after ? (
                            <div className="small muted">
                              {item.primary_endpoint.tls_not_after.slice(0, 10)}
                            </div>
                          ) : null}
                          {item.primary_endpoint.tls_invalid_reason ? (
                            <div className="small muted">
                              {tlsInvalidReason(item.primary_endpoint.tls_invalid_reason)}
                            </div>
                          ) : null}
                        </>
                      ) : (
                        <span className="muted small">未检查</span>
                      )
                    ) : (
                      <span className="muted small">—</span>
                    )}
                  </td>
                  <td>
                    {(() => {
                      const info = item.status.release_info;
                      // 有仓库：当前 → 最新（落后标黄）；没仓库：只显示镜像识别到的版本
                      const current = info?.current_version ?? item.status.image_version;
                      if (!current && !info) return <span className="muted small">—</span>;
                      // 镜像 label 与 GitHub tag 的 v 前缀习惯不同（6.18.0 vs v6.18.0），比较前归一化
                      const norm = (v: string) => v.replace(/^v/i, "");
                      const behind =
                        info?.latest_version != null &&
                        info.current_version != null &&
                        norm(info.current_version) !== norm(info.latest_version);
                      // 当前版本未知时没法比较，不能标「最新」，只能标「未同步」
                      const comparable = info?.current_version != null;
                      return (
                        <div className="badge-stack">
                          <span className="mono small">{current ?? "—"}</span>
                          {behind ? (
                            <>
                              <span className="mono small">→ {info.latest_version}</span>
                              <span className="badge warn">有更新</span>
                            </>
                          ) : info?.latest_version && comparable ? (
                            <span className="badge ok">最新</span>
                          ) : info ? (
                            <span className="badge muted">未同步</span>
                          ) : null}
                        </div>
                      );
                    })()}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="btn btn-mini"
                        type="button"
                        onClick={() => startEditInfo(item)}
                        aria-label={`编辑「${item.name}」`}
                      >
                        编辑
                      </button>
                      <button
                        className="btn btn-mini danger"
                        type="button"
                        onClick={() => void removeService(item)}
                        aria-label={`从台账移除「${item.name}」`}
                      >
                        移除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="small muted">
        共 {total} 个服务，当前显示 {tabItems.length} 个
        {tagFilter.length > 0 ? `（标签筛选：${tagFilter.join("、")}）` : ""}
      </p>
      <p className="small muted">
        服务器端口取自主入口 URL，省略端口时按 https→443、http→80 推断。
      </p>
      {editingInfo ? (
        <ServiceInfoEditor
          title={editingInfo.name}
          name={editingInfo.name}
          description={editingInfo.description}
          endpointUrl={editingInfo.primary_endpoint?.url ?? null}
          releaseOwner={editingInfo.status.release_info?.owner ?? null}
          releaseRepo={editingInfo.status.release_info?.repo ?? null}
          installedTagNote={editingInfo.status.release_info?.installed_tag_note ?? ""}
          busy={savingInfo}
          onSave={(values) => void saveInfo(values)}
          onClose={cancelEditInfo}
        />
      ) : null}
      {editingTags ? (
        <TagEditor
          title={editingTags.name}
          tags={editingTags.tags}
          allTags={allTags}
          busy={savingTags}
          onSave={(tags) => void saveTags(tags)}
          onClose={() => setEditingTags(null)}
        />
      ) : null}
      <Toast message={toast} kind={toastKind} onDismiss={() => setToast(null)} />
    </>
  );
}
