"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type CertificateOverviewRow,
  type DomainOverviewRow,
  type PortOverviewResponse,
} from "@/lib/api";
import {
  formatTime,
  portKindLabel,
  portText,
  tlsInvalidReason,
  tlsTone,
} from "@/lib/status";
import SessionGate from "@/components/SessionGate";
import { SafeLink, StateBadge, Toast } from "@/components/Widgets";

type Tab = "ports" | "domains" | "certificates";

export default function ResourcesPage() {
  return (
    <SessionGate>
      <ResourcesView />
    </SessionGate>
  );
}

function ResourcesView() {
  const [tab, setTab] = useState<Tab>("ports");
  const [query, setQuery] = useState("");
  const [onlyRegistered, setOnlyRegistered] = useState(false);
  const [ports, setPorts] = useState<PortOverviewResponse | null>(null);
  const [domains, setDomains] = useState<DomainOverviewRow[]>([]);
  const [certs, setCerts] = useState<CertificateOverviewRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [toast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      if (tab === "ports") {
        setPorts(await api.ports({ only_registered: onlyRegistered, query }));
      } else if (tab === "domains") {
        const result = await api.domains({ query });
        setDomains(result.items);
      } else {
        const result = await api.certificates({ query });
        setCerts(result.items);
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "加载失败");
    }
  }, [tab, query, onlyRegistered]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <h1>资源总览</h1>
      <p className="lead">
        端口、域名和证书共用同一份台账数据，可以从任一处跳到对应服务。
      </p>

      <div className="tabs" role="tablist">
        <button
          role="tab"
          aria-selected={tab === "ports"}
          className={tab === "ports" ? "active" : ""}
          onClick={() => setTab("ports")}
        >
          端口
        </button>
        <button
          role="tab"
          aria-selected={tab === "domains"}
          className={tab === "domains" ? "active" : ""}
          onClick={() => setTab("domains")}
        >
          域名
        </button>
        <button
          role="tab"
          aria-selected={tab === "certificates"}
          className={tab === "certificates" ? "active" : ""}
          onClick={() => setTab("certificates")}
        >
          证书
        </button>
      </div>

      <div className="card tight">
        <div className="btn-row">
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索主机 / 端口 / 服务"
            aria-label="搜索资源"
            style={{ flex: "1 1 260px" }}
          />
          {tab === "ports" ? (
            <label className="small" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={onlyRegistered}
                onChange={(event) => setOnlyRegistered(event.target.checked)}
              />
              仅已登记服务
            </label>
          ) : null}
        </div>
      </div>

      {error ? <p className="notice bad">{error}</p> : null}

      {tab === "ports" && ports ? (
        <>
          <div className="notice info">
            <span>{ports.scope_note}</span>
          </div>
          {ports.overlaps.length ? (
            <div className="notice">
              <div>
                <strong>潜在端口重叠（需人工核查）</strong>
                <ul className="small" style={{ margin: "6px 0 0 16px", padding: 0 }}>
                  {ports.overlaps.map((pair) => (
                    <li key={`${pair.left}-${pair.right}`} className="mono">
                      {pair.left} ↔ {pair.right}
                    </li>
                  ))}
                </ul>
                <p className="small" style={{ margin: "6px 0 0" }}>
                  仅同主机、同协议、同地址族且绑定 IP 重叠时提示；不代表 Docker 已成功运行冲突绑定。
                </p>
              </div>
            </div>
          ) : null}
          {ports.items.length === 0 ? (
            <p className="muted">没有端口记录。若 Docker 读取不可用，请到「设置」查看原因。</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>端口</th>
                    <th>类型</th>
                    <th>容器</th>
                    <th>服务</th>
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {ports.items.map((row, index) => (
                    <tr key={`${row.source_key}-${row.host_port}-${row.container_port}-${index}`}>
                      <td className="mono">{portText(row)}</td>
                      <td className="small">{portKindLabel(row.kind)}</td>
                      <td className="small">
                        {row.container_name || "—"}
                        {row.project ? <div className="muted">{row.project}</div> : null}
                      </td>
                      <td className="small">
                        {row.service_id ? (
                          <Link href={`/service/${row.service_id}`}>{row.service_name}</Link>
                        ) : (
                          <span className="muted">未登记</span>
                        )}
                      </td>
                      <td className="small">
                        {row.origin === "manual" ? "人工" : "Docker"}
                        {row.note ? <div className="muted">{row.note}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}

      {tab === "domains" ? (
        domains.length === 0 ? (
          <p className="muted">暂无可展示的域名：域名视图从入口 URL 推导，无对外入口的服务不产生域名。</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>域名</th>
                  <th>端口</th>
                  <th>路径</th>
                  <th>服务</th>
                  <th>证书</th>
                  <th>反代目标（人工登记）</th>
                </tr>
              </thead>
              <tbody>
                {domains.map((row) => (
                  <tr key={row.endpoint_id}>
                    <td>
                      <SafeLink className="mono" href={row.url}>
                        {row.host}
                      </SafeLink>
                      {row.is_ip ? <div className="small muted">IP 入口</div> : null}
                    </td>
                    <td className="mono">{row.port ?? (row.scheme === "https" ? 443 : 80)}</td>
                    <td className="mono small">{row.path}</td>
                    <td className="small">
                      <Link href={`/service/${row.service_id}`}>{row.service_name}</Link>
                      <div className="muted">
                        {row.endpoint_label || "入口"} · {row.endpoint_kind}
                      </div>
                    </td>
                    <td>
                      <StateBadge
                        tone={tlsTone(row.tls_state, row.tls_invalid_reason)}
                      />
                      {row.tls_days_remaining !== null ? (
                        <div className="small muted">{row.tls_days_remaining} 天</div>
                      ) : null}
                    </td>
                    <td className="small mono wrap-anywhere">
                      {row.route_target
                        ? `${row.route_target.scheme}://${row.route_target.host}${
                            row.route_target.port ? `:${row.route_target.port}` : ""
                          }${row.route_target.path_prefix}`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      {tab === "certificates" ? (
        certs.length === 0 ? (
          <p className="muted">还没有可检查的 HTTPS 入口。</p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>主机:端口</th>
                  <th>状态</th>
                  <th>到期</th>
                  <th>签发者</th>
                  <th>被哪些入口共用</th>
                </tr>
              </thead>
              <tbody>
                {certs.map((row) => (
                  <tr key={`${row.host}:${row.port}`}>
                    <td className="mono">
                      {row.host}:{row.port}
                    </td>
                    <td>
                      <StateBadge
                        tone={tlsTone(row.tls_state, row.invalid_reason)}
                      />
                      {row.invalid_reason ? (
                        <div className="small muted">{tlsInvalidReason(row.invalid_reason)}</div>
                      ) : null}
                    </td>
                    <td className="small">
                      {row.not_after ? formatTime(row.not_after) : "—"}
                      {row.days_remaining !== null ? (
                        <div className="muted">
                          {row.days_remaining < 0 ? "已过期" : `剩 ${row.days_remaining} 天`}
                        </div>
                      ) : null}
                    </td>
                    <td className="small wrap-anywhere">{row.issuer || "—"}</td>
                    <td className="small">
                      {row.used_by.length ? row.used_by.join("、") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      <Toast message={toast} />
    </>
  );
}
