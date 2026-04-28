"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { api, Account } from "@/lib/api";

function StatusDot({ active }: { active: boolean }) {
  return (
    <span className="inline-block w-2 h-2 rounded-full mr-2 shrink-0"
      style={{ background: active ? "var(--success)" : "var(--muted)" }} />
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--muted)" }}>
        {title}
      </p>
      {children}
    </div>
  );
}

function StatBlock({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="flex-1 rounded-lg p-4 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <p className="text-2xl font-bold" style={{ color: color ?? "var(--foreground)" }}>{value}</p>
      <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>{label}</p>
    </div>
  );
}

function logColor(line: string): string {
  if (line.includes("[ERROR]") || line.includes("错误") || line.includes("失败") || line.includes("异常")) return "#f87171";
  if (line.includes("[WARNING]") || line.includes("警告") || line.includes("WARNING")) return "#fbbf24";
  if (line.includes("[INFO]")) return "#c9d1d9";
  return "#8b949e";
}

export default function Home() {
  const [accounts, setAccounts]         = useState<Account[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [publishedCount, setPublishedCount] = useState(0);
  const [failedCount, setFailedCount]   = useState(0);
  const [loading, setLoading]           = useState(true);
  const [publishing, setPublishing]     = useState(false);
  const [publishRunning, setPublishRunning] = useState(false);
  const [cancelling, setCancelling]     = useState(false);
  const [publishResult, setPublishResult] = useState<{ synced: number; published: number } | null>(null);

  const [logs, setLogs]               = useState<string[]>([]);
  const [logPaused, setLogPaused]     = useState(false);
  const [logExpanded, setLogExpanded] = useState(true);
  const logTimerRef     = useRef<ReturnType<typeof setInterval> | null>(null);
  const logsEndRef      = useRef<HTMLDivElement>(null);
  const logInitScrolled = useRef(false);

  useEffect(() => {
    api.accounts.list().then(accs => {
      setAccounts(accs);
      const id = accs[0]?.id ?? 1;
      return Promise.all([
        api.content.list(id, "pending_review"),
        api.content.list(id, "published"),
        api.content.list(id, "failed"),
      ]);
    }).then(([pending, published, failed]) => {
      setPendingCount(pending.length);
      setPublishedCount(published.length);
      setFailedCount(failed.length);
    }).finally(() => setLoading(false));
  }, []);

  const triggerCancel = useCallback(async () => {
    setCancelling(true);
    try {
      const res = await api.content.cancelPublish();
      if (!res.cancelled) setCancelling(false); // 没有任务在跑，立即还原
    } catch {
      setCancelling(false);
    }
  }, []);

  const triggerPublish = useCallback(async () => {
    setPublishing(true);
    setPublishResult(null);
    try {
      const res = await api.content.publishNow();
      setPublishResult({ synced: res.synced ?? 0, published: res.published ?? 0 });
      // 刷新发布数量
      const id = accounts[0]?.id ?? 1;
      api.content.list(id, "published").then(r => setPublishedCount(r.length));
    } catch (e) {
      setPublishResult({ synced: -1, published: -1 });
    } finally {
      setPublishing(false);
      setTimeout(() => setPublishResult(null), 5000);
    }
  }, [accounts]);

  useEffect(() => {
    const check = () => {
      api.content.publishRunning().then(r => {
        setPublishRunning(r.running);
        if (!r.running) setCancelling(false);
      }).catch(() => {});
    };
    check();
    const t = setInterval(check, 4000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const fetch = () => {
      if (logPaused) return;
      api.settings.logs(200).then(r => {
        setLogs(r.lines);
        if (!logInitScrolled.current && r.lines.length > 0) {
          logInitScrolled.current = true;
          setTimeout(() => logsEndRef.current?.scrollIntoView(), 50);
        }
      }).catch(() => {});
    };
    fetch();
    logTimerRef.current = setInterval(fetch, 3000);
    return () => { if (logTimerRef.current) clearInterval(logTimerRef.current); };
  }, [logPaused]);

  if (loading) return <p className="text-sm mt-4" style={{ color: "var(--muted)" }}>加载中…</p>;

  if (accounts.length === 0) {
    return (
      <div className="mt-8 text-center">
        <p className="mb-4" style={{ color: "var(--muted)" }}>还没有账号</p>
        <Link href="/login" className="text-sm underline" style={{ color: "var(--accent)" }}>去账号管理</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">总览</h1>

      {/* 账号状态 + 快捷操作 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        <Card title={`账号状态（${accounts.length}）`}>
          <div className="flex flex-wrap gap-2 overflow-y-auto pr-1" style={{ maxHeight: 200 }}>
            {accounts.map(acc => {
              const loggedIn = acc.login_status === "logged_in";
              const name = acc.display_name || acc.nickname || `账号 ${acc.id}`;
              return (
                <span key={acc.id}
                  className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
                  style={{
                    background: loggedIn
                      ? "color-mix(in srgb, var(--success) 12%, transparent)"
                      : "var(--background)",
                    border: `1px solid ${loggedIn ? "color-mix(in srgb, var(--success) 35%, transparent)" : "var(--border)"}`,
                    color: loggedIn ? "var(--success)" : "var(--muted)",
                  }}>
                  <span className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ background: loggedIn ? "var(--success)" : "var(--muted)" }} />
                  <span style={{ color: "var(--foreground)" }}>{name}</span>
                  <span>{loggedIn ? "已登录" : "未登录"}</span>
                </span>
              );
            })}
          </div>
          {accounts.some(a => a.login_status !== "logged_in") && (
            <Link href="/login" className="mt-3 inline-block text-xs px-3 py-1.5 rounded"
              style={{ background: "var(--accent)", color: "#fff" }}>
              前往账号管理
            </Link>
          )}
        </Card>

        <Card title="快捷操作">
          <div className="flex gap-2">
            <Link href="/write"
              className="flex-1 text-center text-xs px-3 py-2.5 rounded font-medium whitespace-nowrap"
              style={{ background: "var(--accent)", color: "#fff" }}>
              写文案
            </Link>
            <Link href="/login"
              className="flex-1 text-center text-xs px-3 py-2.5 rounded whitespace-nowrap"
              style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
              账号管理
            </Link>
            <button onClick={triggerPublish} disabled={publishing || publishRunning}
              className="flex-1 text-xs px-3 py-2.5 rounded whitespace-nowrap disabled:opacity-50 transition-colors"
              style={{ border: "1px solid var(--border)", color: "var(--foreground)", background: "var(--surface)" }}>
              {publishing ? "发布中…" : publishRunning ? "运行中…" : "立即发布"}
            </button>
            <button onClick={triggerCancel} disabled={!publishRunning || cancelling}
              className="flex-1 text-xs px-3 py-2.5 rounded whitespace-nowrap disabled:opacity-50 transition-colors"
              style={{
                border: `1px solid ${publishRunning && !cancelling ? "#ef4444" : "var(--border)"}`,
                color: publishRunning && !cancelling ? "#ef4444" : "var(--muted)",
                background: "var(--surface)",
              }}>
              {cancelling ? "终止中…" : "终止任务"}
            </button>
          </div>
          {publishResult && (
            <p className="text-xs mt-2"
              style={{ color: publishResult.published < 0 ? "#ef4444" : "var(--success)" }}>
              {publishResult.published < 0
                ? "发布失败，请检查 MCP 和飞书配置"
                : publishResult.published === 0 && publishResult.synced === 0
                  ? "暂无待发布内容"
                  : `同步 ${publishResult.synced} 条，发布 ${publishResult.published} 条`}
            </p>
          )}
        </Card>
      </div>

      {/* 数据统计 */}
      <div className="flex gap-4">
        <StatBlock label="已发布" value={publishedCount} color="var(--success)" />
        <StatBlock label="待审核" value={pendingCount}
          color={pendingCount > 0 ? "var(--warning)" : undefined} />
        <StatBlock label="发布失败" value={failedCount}
          color={failedCount > 0 ? "var(--accent)" : undefined} />
      </div>

      {/* 运行日志 */}
      <div className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
        <div className="flex items-center justify-between px-4 py-2.5 cursor-pointer select-none"
          style={{ background: "var(--surface)", borderBottom: logExpanded ? "1px solid var(--border)" : "none" }}
          onClick={() => setLogExpanded(v => !v)}>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>
              运行日志
            </span>
            <span className="w-1.5 h-1.5 rounded-full inline-block"
              style={{ background: logPaused ? "var(--muted)" : "#22c55e" }} />
          </div>
          <div className="flex items-center gap-3" onClick={e => e.stopPropagation()}>
            <button onClick={() => setLogPaused(v => !v)}
              className="text-xs px-2 py-0.5 rounded"
              style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
              {logPaused ? "▶ 继续" : "⏸ 暂停"}
            </button>
            <button onClick={() => setLogs([])}
              className="text-xs px-2 py-0.5 rounded"
              style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
              清屏
            </button>
            <span className="text-xs" style={{ color: "var(--muted)" }}>{logExpanded ? "▲" : "▼"}</span>
          </div>
        </div>
        {logExpanded && (
          <div className="text-xs font-mono leading-relaxed p-3 overflow-auto"
            style={{ background: "#0d1117", maxHeight: 320 }}>
            {logs.length === 0
              ? <span style={{ color: "#6e7681" }}>暂无日志，等待事件…</span>
              : logs.map((line, i) => (
                <div key={i} style={{ color: logColor(line) }}>{line}</div>
              ))
            }
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  );
}
