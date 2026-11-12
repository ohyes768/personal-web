"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  api,
  ApiError,
  type ComponentView,
  type EndpointRecord,
  type ReleaseListResponse,
  type ServiceDetail,
} from "@/lib/api";
import {
  composeFileText,
  describeCheck,
  formatTime,
  healthTooltip,
  HEALTH,
  portKindLabel,
  portText,
  RELEASE_STATE,
  RUNTIME,
  tlsTooltip,
  TLS_STATE,
  URL_STATE,
} from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { CopyButton, SafeLink, StateBadge, Toast } from "@/components/Widgets";

export default function ServicePage() {
  return (
    <SessionGate>
      <ServiceDetailView />
    </SessionGate>
  );
}

type EndpointDraft = {
  label: string;
  kind: "internal" | "external" | "admin";
  url: string;
  probe_url: string;
  tls_check: boolean;
  expected_status_ranges: string;
  renewal_note: string;
};

const EMPTY_ENDPOINT: EndpointDraft = {
  label: "",
  kind: "external",
  url: "",
  probe_url: "",
  tls_check: true,
  expected_status_ranges: "",
  renewal_note: "",
};

function ServiceDetailView() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [detail, setDetail] = useState<ServiceDetail | null>(null);
  const [releases, setReleases] = useState<ReleaseListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    description: "",
    category: "",
    tags: "",
    notes: "",
  });
  const [endpointDraft, setEndpointDraft] = useState<EndpointDraft | null>(null);
  const [editingEndpointId, setEditingEndpointId] = useState<string | null>(null);
  const [repoDraft, setRepoDraft] = useState("");
  const [tagNote, setTagNote] = useState("");
  const [portDraft, setPortDraft] = useState({ host_ip: "", host_port: "", container_port: "", note: "" });

  const load = useCallback(async () => {
    setError(null);
    try {
      const [loaded, releaseList] = await Promise.all([
        api.getService(id),
        api.listReleases(id).catch(() => null),
      ]);
      setDetail(loaded);
      setReleases(releaseList);
      setDraft({
        name: loaded.name,
        description: loaded.description,
        category: loaded.category,
        tags: loaded.tags.join(", "),
        notes: loaded.notes,
      });
      setRepoDraft(
        loaded.release_source
          ? `${loaded.release_source.owner}/${loaded.release_source.repo}`
          : "",
      );
      setTagNote(loaded.release_source?.installed_tag_note ?? "");
      return loaded;
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载失败");
      return null;
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  function report(caught: unknown, fallback: string) {
    if (caught instanceof ApiError) {
      if (caught.status === 409) {
        setToast(`${caught.message}（请刷新后重试）`);
        void load();
        return;
      }
      setToast(caught.message);
      return;
    }
    setToast(fallback);
  }

  async function saveService(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    try {
      await api.patchService(detail.id, {
        name: draft.name,
        description: draft.description,
        category: draft.category,
        tags: draft.tags
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        notes: draft.notes,
        revision: detail.revision,
      });
      setEditing(false);
      setToast("已保存");
      await load();
    } catch (caught) {
      report(caught, "保存失败");
    }
  }

  async function removeService() {
    if (!detail) return;
    if (
      !window.confirm(
        `从台账移除「${detail.name}」？只删除本应用的记录与关联，运行中的容器不受影响。`,
      )
    ) {
      return;
    }
    try {
      await api.deleteService(detail.id);
      router.push("/");
    } catch (caught) {
      report(caught, "移除失败");
    }
  }

  async function submitEndpoint(event: React.FormEvent) {
    event.preventDefault();
    if (!detail || !endpointDraft) return;
    const body = {
      label: endpointDraft.label,
      kind: endpointDraft.kind,
      url: endpointDraft.url.trim(),
      probe_url: endpointDraft.probe_url.trim() || null,
      enabled: true,
      tls_check: endpointDraft.tls_check,
      expected_status_ranges: endpointDraft.expected_status_ranges
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      renewal_note: endpointDraft.renewal_note,
    };
    try {
      if (editingEndpointId) {
        await api.updateEndpoint(detail.id, editingEndpointId, body);
      } else {
        await api.addEndpoint(detail.id, body);
      }
      setEndpointDraft(null);
      setEditingEndpointId(null);
      setToast("入口已保存");
      await load();
    } catch (caught) {
      report(caught, "保存入口失败");
    }
  }

  async function removeEndpoint(endpoint: EndpointRecord) {
    if (!detail) return;
    if (!window.confirm(`删除入口 ${endpoint.url}？`)) return;
    try {
      await api.deleteEndpoint(detail.id, endpoint.id);
      setToast("入口已删除");
      await load();
    } catch (caught) {
      report(caught, "删除入口失败");
    }
  }

  async function saveRepo(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    const text = repoDraft.trim();
    if (!text) return;
    const match = text.match(/^([\w.-]+)\/([\w.-]+)$/);
    if (!match) {
      setToast("仓库请填 owner/repo 或 GitHub 仓库 URL");
      return;
    }
    try {
      await api.setReleaseSource(detail.id, {
        owner: match[1],
        repo: match[2],
        installed_tag_note: tagNote,
      });
      setToast("仓库已关联");
      await load();
    } catch (caught) {
      report(caught, "关联失败");
    }
  }

  async function checkNow(kind: "url" | "tls" | "releases" | "all") {
    if (!detail) return;
    try {
      const job = await api.refresh(kind, detail.id);
      setToast(job.deduplicated ? "同类检查已在跑" : "已提交检查任务");
      window.setTimeout(() => void load(), 3000);
    } catch (caught) {
      report(caught, "提交失败");
    }
  }

  async function toggleRequired(component: ComponentView) {
    if (!detail) return;
    try {
      await api.setComponentRequired(detail.id, component.source_key, !component.required);
      await load();
    } catch (caught) {
      report(caught, "更新失败");
    }
  }

  async function unbind(component: ComponentView) {
    if (!detail) return;
    if (!window.confirm(`把组件「${component.container_name || component.source_key}」从本服务解绑？容器本身不受影响。`)) {
      return;
    }
    try {
      await api.unbindComponent(detail.id, component.source_key);
      setToast("已解绑");
      await load();
    } catch (caught) {
      report(caught, "解绑失败");
    }
  }

  async function addPort(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    try {
      await api.addPortNote(detail.id, {
        host_ip: portDraft.host_ip,
        host_port: Number(portDraft.host_port),
        container_port: portDraft.container_port ? Number(portDraft.container_port) : null,
        protocol: "tcp",
        note: portDraft.note,
      });
      setPortDraft({ host_ip: "", host_port: "", container_port: "", note: "" });
      setToast("端口已记录");
      await load();
    } catch (caught) {
      report(caught, "记录端口失败");
    }
  }

  async function markRead(releaseIds: number[]) {
    if (!detail || releaseIds.length === 0) return;
    try {
      await api.markReleasesRead(detail.id, releaseIds);
      await load();
    } catch (caught) {
      report(caught, "标记已读失败");
    }
  }

  if (error) {
    return (
      <>
        <p className="notice bad">{error}</p>
        <Link className="btn" href="/">
          返回服务列表
        </Link>
      </>
    );
  }

  if (!detail) {
    return <p className="muted">加载中…</p>;
  }

  const unread = releases?.items.filter((item) => !item.read) ?? [];

  return (
    <>
      <div className="btn-row" style={{ marginBottom: 8 }}>
        <Link className="btn" href="/">
          ← 服务列表
        </Link>
      </div>

      <h1>{detail.name}</h1>
      <p className="lead">{detail.description || "还没有填写用途说明"}</p>

      <div className="card tight">
        <div className="badge-stack" style={{ marginBottom: 8 }}>
          <StateBadge tone={RUNTIME[detail.status.runtime]} />
          <StateBadge
            tone={HEALTH[detail.status.health]}
            title={healthTooltip(detail.components, detail.status.health)}
          />
          <StateBadge tone={URL_STATE[detail.status.url]} title={describeCheck(detail.status.url_check)} />
          <StateBadge
            tone={TLS_STATE[detail.status.tls]}
            title={tlsTooltip(detail.status.tls_check)}
          />
          <StateBadge tone={RELEASE_STATE[detail.status.release]} />
        </div>
        <p className="small muted">
          URL 检查：{describeCheck(detail.status.url_check)} · 证书检查：
          {describeCheck(detail.status.tls_check)} · 发布时间：
          {describeCheck(detail.status.release_check, "未检查")}
        </p>
        <div className="btn-row">
          <button className="btn" type="button" onClick={() => void checkNow("url")}>
            检查 URL
          </button>
          <button className="btn" type="button" onClick={() => void checkNow("tls")}>
            检查证书
          </button>
          <button className="btn" type="button" onClick={() => void checkNow("releases")}>
            检查发布
          </button>
          <button className="btn" type="button" onClick={() => void checkNow("all")}>
            全部检查
          </button>
          <button className="btn" type="button" onClick={() => setEditing((value) => !value)}>
            {editing ? "取消编辑" : "编辑信息"}
          </button>
          <button className="btn danger" type="button" onClick={() => void removeService()}>
            从台账移除
          </button>
        </div>
      </div>

      {editing ? (
        <form className="card" onSubmit={saveService}>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="edit-name">名称</label>
              <input
                id="edit-name"
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="edit-category">分类</label>
              <input
                id="edit-category"
                value={draft.category}
                onChange={(event) => setDraft({ ...draft, category: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="edit-tags">标签（逗号分隔）</label>
              <input
                id="edit-tags"
                value={draft.tags}
                onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="edit-desc">用途</label>
            <textarea
              id="edit-desc"
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="edit-notes">笔记</label>
            <textarea
              id="edit-notes"
              value={draft.notes}
              onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
            />
          </div>
          <button className="btn primary" type="submit">
            保存
          </button>
        </form>
      ) : null}

      <h2>组件（{detail.components.length}）</h2>
      {detail.components.length === 0 ? (
        <div className="card">
          <p className="muted">还没有关联容器组件。</p>
          <Link className="btn" href="/discovery">
            去发现导入
          </Link>
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>容器</th>
                <th>镜像</th>
                <th>状态</th>
                <th>部署路径</th>
                <th>端口</th>
                <th>数据卷</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {detail.components.map((component) => (
                <tr key={component.source_key}>
                  <td>
                    <div className="mono">{component.container_name || "（未找到）"}</div>
                    <div className="small muted">{component.source_key}</div>
                    {component.project ? (
                      <div className="small muted">
                        compose: {component.project}
                        {component.service_name ? ` / ${component.service_name}` : ""}
                      </div>
                    ) : null}
                    <label className="small" style={{ display: "inline-flex", gap: 4, marginTop: 4 }}>
                      <input
                        type="checkbox"
                        checked={component.required}
                        onChange={() => void toggleRequired(component)}
                      />
                      影响运行状态
                    </label>
                  </td>
                  <td className="mono wrap-anywhere">{component.image_ref || "—"}</td>
                  <td>
                    <span className="badge muted">{component.state}</span>
                    {component.health !== "not_configured" ? (
                      <div className="small">
                        <StateBadge
                          tone={HEALTH[component.health]}
                          title="Docker 健康检查"
                        />
                      </div>
                    ) : (
                      <div className="small muted" title="该容器没配 Docker 健康检查">
                        -
                      </div>
                    )}
                    <div className="small muted">观测于 {formatTime(component.last_seen_at)}</div>
                  </td>
                  <td>
                    <div className="mono wrap-anywhere">
                      {component.compose_working_dir ?? "工作目录未知"}
                    </div>
                    {component.compose_files.map((file) => (
                      <div key={file.raw} className="small mono wrap-anywhere">
                        {composeFileText(file)}
                        <CopyButton value={file.resolved ?? file.raw} label="复制" onCopied={setToast} />
                      </div>
                    ))}
                    <div className="small muted">来源：{component.override_source === "manual" ? "人工补录" : "Docker 标签"}</div>
                  </td>
                  <td>
                    {component.ports.length === 0 ? (
                      <span className="muted small">
                        {component.network_mode === "host" ? "共享宿主网络，未自动采集" : "无端口记录"}
                      </span>
                    ) : (
                      component.ports.map((port, index) => (
                        <div key={`${component.source_key}-${index}`} className="small mono">
                          {portText(port)}
                          <span className="muted"> · {portKindLabel(port.kind)}</span>
                        </div>
                      ))
                    )}
                  </td>
                  <td>
                    {component.mounts.length === 0 ? (
                      <span className="muted small">无挂载</span>
                    ) : (
                      component.mounts.map((mount, index) => (
                        <div key={`${component.source_key}-m-${index}`} className="small mono wrap-anywhere">
                          {mount.kind === "bind" ? "bind" : mount.kind}：{mount.source || "（匿名卷）"} →{" "}
                          {mount.destination}
                          {mount.read_only ? "（只读）" : ""}
                        </div>
                      ))
                    )}
                    {component.data_paths.length ? (
                      <div className="small muted wrap-anywhere">
                        数据路径：{component.data_paths.join("、")}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <button className="btn btn-mini" type="button" onClick={() => void unbind(component)}>
                      解绑
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>入口（{detail.endpoints.length}）</h2>
      <div className="card tight">
        <div className="btn-row">
          <button
            className="btn"
            type="button"
            onClick={() => {
              setEndpointDraft({ ...EMPTY_ENDPOINT });
              setEditingEndpointId(null);
            }}
          >
            添加入口
          </button>
        </div>
        {endpointDraft ? (
          <form onSubmit={submitEndpoint} style={{ marginTop: 12 }}>
            <div className="form-grid">
              <div className="field">
                <label htmlFor="ep-label">标签</label>
                <input
                  id="ep-label"
                  value={endpointDraft.label}
                  onChange={(event) => setEndpointDraft({ ...endpointDraft, label: event.target.value })}
                  placeholder="内网 / 公网 / 管理"
                />
              </div>
              <div className="field">
                <label htmlFor="ep-kind">类型</label>
                <select
                  id="ep-kind"
                  value={endpointDraft.kind}
                  onChange={(event) =>
                    setEndpointDraft({
                      ...endpointDraft,
                      kind: event.target.value as EndpointDraft["kind"],
                    })
                  }
                >
                  <option value="external">公网入口</option>
                  <option value="internal">内网入口</option>
                  <option value="admin">管理入口</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="ep-url">URL（浏览器打开）</label>
                <input
                  id="ep-url"
                  type="url"
                  value={endpointDraft.url}
                  onChange={(event) => setEndpointDraft({ ...endpointDraft, url: event.target.value })}
                  placeholder="https://web.duomi77.cn:9443/dividend"
                  required
                />
                <span className="hint">不接受账号密码与凭据类查询参数。</span>
              </div>
              <div className="field">
                <label htmlFor="ep-probe">探测 URL（可选）</label>
                <input
                  id="ep-probe"
                  type="url"
                  value={endpointDraft.probe_url}
                  onChange={(event) =>
                    setEndpointDraft({ ...endpointDraft, probe_url: event.target.value })
                  }
                  placeholder="http://dividend-backend:8092/api/health"
                />
                <span className="hint">
                  默认探测上面的 URL。localhost 会被拒绝——容器内它指管理台自身。
                </span>
              </div>
              <div className="field">
                <label htmlFor="ep-range">期望状态码（可选）</label>
                <input
                  id="ep-range"
                  value={endpointDraft.expected_status_ranges}
                  onChange={(event) =>
                    setEndpointDraft({
                      ...endpointDraft,
                      expected_status_ranges: event.target.value,
                    })
                  }
                  placeholder="200-399"
                />
              </div>
            </div>
            <label className="small" style={{ display: "inline-flex", gap: 6, marginBottom: 12 }}>
              <input
                type="checkbox"
                checked={endpointDraft.tls_check}
                onChange={(event) =>
                  setEndpointDraft({ ...endpointDraft, tls_check: event.target.checked })
                }
              />
              对 HTTPS 入口做证书检查
            </label>
            <div className="field">
              <label htmlFor="ep-renewal">续期备注</label>
              <input
                id="ep-renewal"
                value={endpointDraft.renewal_note}
                onChange={(event) =>
                  setEndpointDraft({ ...endpointDraft, renewal_note: event.target.value })
                }
                placeholder="人工说明，例如 acme.sh 续期"
              />
            </div>
            <div className="btn-row">
              <button className="btn primary" type="submit">
                保存入口
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => {
                  setEndpointDraft(null);
                  setEditingEndpointId(null);
                }}
              >
                取消
              </button>
            </div>
          </form>
        ) : null}
      </div>

      {detail.endpoints.length === 0 ? (
        <p className="muted small">还没有登记入口，URL 与证书维度会一直是「未检查」。</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>标签</th>
                <th>类型</th>
                <th>URL</th>
                <th>证书检查</th>
                <th>续期备注</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {detail.endpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td>{endpoint.label || "—"}</td>
                  <td className="small">{endpoint.kind}</td>
                  <td>
                    <SafeLink className="mono wrap-anywhere" href={endpoint.url}>
                      {endpoint.url}
                    </SafeLink>
                    {endpoint.probe_url ? (
                      <div className="small muted mono wrap-anywhere">探测：{endpoint.probe_url}</div>
                    ) : null}
                  </td>
                  <td className="small">{endpoint.tls_check ? "是" : "否"}</td>
                  <td className="small">{endpoint.renewal_note || "—"}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="btn btn-mini"
                        type="button"
                        onClick={() => {
                          setEndpointDraft({
                            label: endpoint.label,
                            kind: endpoint.kind,
                            url: endpoint.url,
                            probe_url: endpoint.probe_url ?? "",
                            tls_check: endpoint.tls_check,
                            expected_status_ranges: endpoint.expected_status_ranges.join(","),
                            renewal_note: endpoint.renewal_note,
                          });
                          setEditingEndpointId(endpoint.id);
                        }}
                      >
                        编辑
                      </button>
                      <button
                        className="btn btn-mini"
                        type="button"
                        onClick={() => void removeEndpoint(endpoint)}
                      >
                        删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2>人工端口（{detail.port_notes.length}）</h2>
      <p className="small muted">
        用于 host 网络或宿主进程端口；这里记录的是人工信息，不是实测结果。
      </p>
      <form className="card tight" onSubmit={addPort}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="pn-ip">绑定 IP</label>
            <input
              id="pn-ip"
              value={portDraft.host_ip}
              onChange={(event) => setPortDraft({ ...portDraft, host_ip: event.target.value })}
              placeholder="0.0.0.0"
            />
          </div>
          <div className="field">
            <label htmlFor="pn-port">宿主端口</label>
            <input
              id="pn-port"
              type="number"
              value={portDraft.host_port}
              onChange={(event) => setPortDraft({ ...portDraft, host_port: event.target.value })}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="pn-cport">容器端口</label>
            <input
              id="pn-cport"
              type="number"
              value={portDraft.container_port}
              onChange={(event) =>
                setPortDraft({ ...portDraft, container_port: event.target.value })
              }
            />
          </div>
          <div className="field">
            <label htmlFor="pn-note">备注</label>
            <input
              id="pn-note"
              value={portDraft.note}
              onChange={(event) => setPortDraft({ ...portDraft, note: event.target.value })}
            />
          </div>
        </div>
        <button className="btn" type="submit">
          记录端口
        </button>
      </form>
      {detail.port_notes.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>绑定</th>
                <th>备注</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {detail.port_notes.map((note) => (
                <tr key={note.id}>
                  <td className="mono">
                    {note.host_ip || "0.0.0.0"}:{note.host_port}
                    {note.container_port ? ` → ${note.container_port}` : ""}/{note.protocol}
                  </td>
                  <td className="small">{note.note || "—"}</td>
                  <td>
                    <button
                      className="btn btn-mini"
                      type="button"
                      onClick={async () => {
                        try {
                          await api.deletePortNote(detail.id, note.id);
                          await load();
                        } catch (caught) {
                          report(caught, "删除失败");
                        }
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <h2>发布动态</h2>
      <form className="card tight" onSubmit={saveRepo}>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="repo">GitHub 仓库（owner/repo）</label>
            <input
              id="repo"
              value={repoDraft}
              onChange={(event) => setRepoDraft(event.target.value)}
              placeholder="zzet/immich"
            />
          </div>
          <div className="field">
            <label htmlFor="tag-note">人工版本备注</label>
            <input
              id="tag-note"
              value={tagNote}
              onChange={(event) => setTagNote(event.target.value)}
              placeholder="当前跑的是哪个版本（人工填写）"
            />
          </div>
        </div>
        <div className="btn-row">
          <button className="btn" type="submit">
            保存仓库
          </button>
          {detail.release_source ? (
            <button
              className="btn"
              type="button"
              onClick={async () => {
                try {
                  await api.deleteReleaseSource(detail.id);
                  setRepoDraft("");
                  await load();
                } catch (caught) {
                  report(caught, "解除关联失败");
                }
              }}
            >
              解除关联
            </button>
          ) : null}
        </div>
        <p className="small muted">
          安装版本来自人工备注与实际镜像，不与 Release 自动比较。
        </p>
      </form>

      {releases?.check?.check_status === "error" ? (
        <p className="notice bad">
          发布检查失败：{releases.check.error_message ?? releases.check.error_code}
        </p>
      ) : null}
      {releases?.truncated ? (
        <p className="notice">仅覆盖最近 300 条发布，更早的区间未抓取。</p>
      ) : null}

      {!detail.release_source ? (
        <p className="muted small">还没有关联仓库，发布维度显示「未关联仓库」。</p>
      ) : releases && releases.items.length === 0 ? (
        <p className="muted small">
          {releases.check?.current_state === "no_releases"
            ? "该仓库没有正式发布（或只有预发布）。"
            : "还没有缓存到发布，先点一次「检查发布」。"}
        </p>
      ) : (
        <>
          {unread.length ? (
            <div className="btn-row" style={{ marginBottom: 8 }}>
              <button
                className="btn btn-mini"
                type="button"
                onClick={() => void markRead(unread.map((item) => item.release_id))}
              >
                全部标为已读（{unread.length}）
              </button>
            </div>
          ) : null}
          {releases?.items.map((item) => (
            <div className="card tight" key={item.release_id}>
              <div className="btn-row" style={{ justifyContent: "space-between" }}>
                <div>
                  <strong>{item.name || item.tag}</strong>{" "}
                  <span className="badge muted">{item.tag}</span>{" "}
                  {item.read ? null : <span className="badge info">未读</span>}
                  <div className="small muted">
                    发布于 {formatTime(item.published_at)}
                    {releases.latest_release_id === item.release_id ? " · GitHub 标注的最新正式版" : ""}
                  </div>
                </div>
                <div className="row-actions">
                  <SafeLink className="btn btn-mini" href={item.html_url}>
                    在 GitHub 打开
                  </SafeLink>
                  {item.read ? null : (
                    <button
                      className="btn btn-mini"
                      type="button"
                      onClick={() => void markRead([item.release_id])}
                    >
                      标为已读
                    </button>
                  )}
                </div>
              </div>
              <div className="release-body">{item.body || "（无更新说明）"}</div>
            </div>
          ))}
        </>
      )}

      <Toast message={toast} />
    </>
  );
}
