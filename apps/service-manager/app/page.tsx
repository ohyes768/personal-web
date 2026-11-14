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
  healthTooltip,
  HEALTH,
  RUNTIME,
  tlsEndpointTooltip,
  tlsInvalidReason,
  tlsTone,
} from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { SafeLink, Spinner, StateBadge, Toast } from "@/components/Widgets";
import { TagBadge } from "@/components/TagBadge";
import { ServiceInfoEditor } from "@/components/ServiceInfoEditor";
import { TagEditor } from "@/components/TagEditor";
import { TagFilterBar } from "@/components/TagFilterBar";

export default function HomePage() {
  return (
    <SessionGate>
      <ServiceList />
    </SessionGate>
  );
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

  function toggleTagFilter(tag: string) {
    setTagFilter((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    );
  }

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
      setToast("标签已保存");
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "保存标签失败");
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

  async function saveInfo(values: { name: string; description: string; url: string | null }) {
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
      cancelEditInfo();
      setToast(values.url ? "已保存，主入口已登记" : "已保存");
      await load();
      if (values.url) {
        // 触发一次该服务的证书检查，别让用户干等下一轮定时
        try {
          await api.refresh("tls", editingInfo.id);
        } catch {
          // 检查提交失败不影响保存结果
        }
      }
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "保存失败");
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
      setToast("已移除");
      await load();
    } catch (caught) {
      setToast(caught instanceof ApiError ? caught.message : "移除失败");
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
      setToast(
        job.deduplicated
          ? "已有同类型任务在跑，复用现有任务"
          : `已提交${label}任务`,
      );
      // 任务在后台跑，轮询到终态再刷新列表——固定等 3 秒会漏掉慢任务的结果。
      const result = await waitForJob(job.id, { signal: controller.signal });
      if (result.aborted) return;
      if (result.timedOut) {
        setToast(`${label}还没跑完，仍在后台执行，稍后再看`);
      } else if (result.job) {
        setToast(describeJob(label, result.job));
      }
      await load();
    } catch (caught) {
      if (!controller.signal.aborted) {
        setToast(caught instanceof ApiError ? caught.message : `${label}失败`);
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
      <p className="lead">
        台账里的服务、它们对应的容器，以及运行与健康两个状态。名称、用途、标签都在这一页就地改。
      </p>

      {summary ? (
        <div className="kpi-row">
          <div className="kpi">
            <div className="num">{summary.services}</div>
            <div className="lbl">业务服务</div>
          </div>
          <div
            className="kpi"
            title={`上次扫描观测到的容器总数：运行 ${summary.docker_running} · 已消失 ${summary.docker_missing}`}
          >
            <div className="num">{summary.docker_components}</div>
            <div className="lbl">发现容器</div>
          </div>
          <div
            className="kpi"
            title={`已关联到业务服务的容器：${summary.components} / ${summary.docker_components}`}
          >
            <div className="num">{summary.components}</div>
            <div className="lbl">已关联组件</div>
          </div>
          <div
            className="kpi"
            title={`发现但没关联到任何业务服务的容器：${summary.unregistered_components} 个，其中 ${summary.ignored_components} 个已标记忽略，实际待处理 ${summary.unregistered_components - summary.ignored_components} 个`}
          >
            <div
              className="num"
              style={{
                color:
                  summary.unregistered_components - summary.ignored_components > 0
                    ? "var(--warn)"
                    : undefined,
              }}
            >
              {summary.unregistered_components}
            </div>
            <div className="lbl">未入账</div>
          </div>
          <div className="kpi">
            <div className="num small" style={{ fontSize: 13 }}>
              {formatRelative(summary.docker_last_success_at)}
            </div>
            <div className="lbl">上次扫描</div>
          </div>
        </div>
      ) : null}

      {summary && !summary.docker_available ? (
        <div className="notice">
          <span>Docker 读取不可用：{summary.docker_error ?? "未配置"}。人工台账仍可正常使用。</span>
        </div>
      ) : null}

      <div className="card tight">
        <div className="btn-row">
          <input
            type="search"
            placeholder="搜索名称 / 用途 / 标签 / 域名 / 端口 / 路径"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="搜索服务"
            style={{ flex: "1 1 320px" }}
          />
          <button
            className="btn"
            type="button"
            disabled={pending.docker}
            aria-busy={pending.docker}
            title="重新扫描 Docker 容器，刷新「发现容器 / 已关联组件 / 未入账」与各服务的运行、健康状态"
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
        </div>

        <p className="small muted" style={{ marginTop: 8 }}>
          扫描容器：重新读取 Docker 容器状态与健康检查（后台每 60 秒自动扫一次）。
        </p>

        <TagFilterBar allTags={allTags} selected={tagFilter} onChange={setTagFilter} />
      </div>

      {error ? <p className="notice bad">{error}</p> : null}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : tabItems.length === 0 ? (
        <div className="card">
          <p>
            {items.length === 0
              ? "台账还是空的。到「发现导入」从运行中的容器建立台账条目。"
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
              去发现导入
            </Link>
          </div>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>服务</th>
                <th>主入口</th>
                <th>运行</th>
                <th>健康</th>
                <th title="HTTPS 证书：有没有人信它、什么时候到期">证书</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tabItems.map((item) => (
                <tr key={item.id} data-service-id={item.id}>
                  <td>
                    <span className="service-name">{item.name}</span>
                    {item.description ? (
                      <div className="small truncate" title={item.description}>
                        {item.description}
                      </div>
                    ) : null}
                    <div className="tag-row" style={{ marginTop: 2 }}>
                      {item.tags.map((tag) => (
                        <TagBadge
                          key={tag}
                          tag={tag}
                          active={tagFilter.includes(tag)}
                          onClick={() => toggleTagFilter(tag)}
                        />
                      ))}
                      <button
                        type="button"
                        className="tag-add"
                        onClick={() => setEditingTags(item)}
                        aria-label={`编辑 ${item.name} 的标签`}
                        title="编辑标签"
                      >
                        ＋标签
                      </button>
                    </div>
                  </td>
                  <td>
                    {item.primary_endpoint ? (
                      <SafeLink
                        href={item.primary_endpoint.url}
                        className="mono wrap-anywhere"
                        title="已登记的主入口不在台账里改"
                      >
                        {item.primary_endpoint.url}
                      </SafeLink>
                    ) : (
                      <span className="muted small">无对外入口</span>
                    )}
                  </td>
                  <td>
                    <StateBadge tone={RUNTIME[item.status.runtime]} />
                    <div className="small muted">{item.component_count} 个组件</div>
                  </td>
                  <td>
                    <StateBadge
                      tone={HEALTH[item.status.health]}
                      title={healthTooltip(undefined, item.status.health)}
                    />
                  </td>
                  <td>
                    {item.primary_endpoint?.tls_check ? (
                      <>
                        <StateBadge
                          tone={tlsTone(
                            (item.primary_endpoint.tls_state ?? "unknown") as never,
                            item.primary_endpoint.tls_invalid_reason,
                          )}
                          title={tlsEndpointTooltip(item.primary_endpoint)}
                        />
                        {item.primary_endpoint.tls_days_remaining !== null &&
                        item.primary_endpoint.tls_days_remaining >= 0 ? (
                          <div className="small muted">
                            {item.primary_endpoint.tls_days_remaining} 天
                          </div>
                        ) : null}
                        {item.primary_endpoint.tls_invalid_reason ? (
                          <div className="small muted">
                            {tlsInvalidReason(item.primary_endpoint.tls_invalid_reason)}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <span className="muted small">-</span>
                    )}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="btn btn-mini"
                        type="button"
                        onClick={() => startEditInfo(item)}
                        aria-label={`编辑「${item.name}」的名称与用途`}
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
      {editingInfo ? (
        <ServiceInfoEditor
          title={editingInfo.name}
          name={editingInfo.name}
          description={editingInfo.description}
          endpointUrl={editingInfo.primary_endpoint?.url ?? null}
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
      <Toast message={toast} />
    </>
  );
}
