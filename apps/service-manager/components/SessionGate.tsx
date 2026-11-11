"use client";

/** 会话门禁：未登录时只渲染登录表单，登录成功后渲染 children。 */

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";

type State = "loading" | "anonymous" | "authenticated";

export default function SessionGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<State>("loading");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .session()
      .then((result) => {
        if (cancelled) return;
        setState(result.authenticated ? "authenticated" : "anonymous");
      })
      .catch(() => {
        if (!cancelled) setState("anonymous");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      setPassword("");
      setState("authenticated");
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(
          caught.status === 429
            ? "尝试过于频繁，请稍后再试"
            : caught.message,
        );
      } else {
        setError("登录失败，请重试");
      }
    } finally {
      setBusy(false);
    }
  }

  if (state === "loading") {
    return <p className="muted">正在检查会话…</p>;
  }

  if (state === "anonymous") {
    return (
      <form className="gate card" onSubmit={submit}>
        <h1>服务管理台</h1>
        <p className="lead">需要管理员口令才能查看台账。</p>
        <div className="field">
          <label htmlFor="admin-password">管理口令</label>
          <input
            id="admin-password"
            type="password"
            value={password}
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>
        {error ? (
          <p className="notice bad" role="alert">
            {error}
          </p>
        ) : null}
        <button className="btn primary" type="submit" disabled={busy || !password}>
          {busy ? "登录中…" : "登录"}
        </button>
      </form>
    );
  }

  return <>{children}</>;
}

export async function logout(): Promise<void> {
  await api.logout();
  window.location.reload();
}
