"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api, Account } from "@/lib/api";

type Phase = "idle" | "starting" | "qr" | "polling" | "done";

const inputBase = "w-full text-sm px-3 py-2 rounded outline-none";
const inputStyle = { background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" };

const PRESET_TIMES = ["06:00","07:00","08:00","09:00","10:00","11:00","12:00","13:00",
  "14:00","15:00","16:00","17:00","18:00","19:00","20:00","21:00","22:00","23:00"];
const DAY_LABELS = ["一","二","三","四","五","六","日"];

type SchedMode = "frequency" | "interval" | "times";

export default function AccountLoginCard({
  account: initialAccount, onDelete, defaultCollapsed,
}: {
  account: Account;
  onDelete: (id: number) => Promise<void>;
  defaultCollapsed: boolean;
}) {
  const [account, setAccount] = useState<Account>(initialAccount);
  const [phase, setPhase]     = useState<Phase>(initialAccount.login_status === "logged_in" ? "done" : "idle");
  const [qrImg, setQrImg]     = useState("");
  const [msg, setMsg]         = useState("");
  const stopRef = useRef(false);

  // 备注名
  const [displayName, setDisplayName] = useState(initialAccount.display_name ?? "");
  const [savingName, setSavingName]   = useState(false);


  // 验证
  const [verifying, setVerifying]       = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ logged_in: boolean; nickname?: string; error?: string } | null>(null);

  // 日志
  const [logs, setLogs]   = useState<string[]>([]);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 折叠
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  // 飞书
  const [feishuEdits, setFeishuEdits]         = useState({
    app_token: initialAccount.feishu_app_token ?? "",
    table_id:  initialAccount.feishu_table_id  ?? "",
  });
  const [savingFeishu, setSavingFeishu]       = useState(false);
  const [setupingFeishu, setSetupingFeishu]   = useState(false);
  const [feishuSetupMsg, setFeishuSetupMsg]   = useState<string | null>(null);
  const [testingFeishu, setTestingFeishu]     = useState(false);
  const [feishuTestResult, setFeishuTestResult] = useState<Record<string, string> | null>(null);

  // 排期
  const parseSched = (raw: string | null) => {
    if (!raw) return { mode: "frequency" as SchedMode, weekly: 3, hours: 8, times: ["09:00"], days: [0,1,2,3,4,5,6], imageMode: "random", contentType: "auto", pillar: "auto" };
    try {
      const s = JSON.parse(raw);
      return {
        mode: (s.mode || "frequency") as SchedMode,
        weekly: s.weekly_count ?? 3,
        hours: s.interval_hours ?? 8,
        times: s.times ?? ["09:00"],
        days: s.days ?? [0,1,2,3,4,5,6],
        imageMode: s.image_mode || "random",
        contentType: s.content_type || "auto",
        pillar: s.pillar || "auto",
      };
    } catch { return { mode: "frequency" as SchedMode, weekly: 3, hours: 8, times: ["09:00"], days: [0,1,2,3,4,5,6], imageMode: "auto", contentType: "auto", pillar: "auto" }; }
  };
  const initSched = parseSched(initialAccount.generate_schedule_json);
  const [schedEnabled, setSchedEnabled]     = useState(initialAccount.auto_generate_enabled);
  const [schedMode, setSchedMode]           = useState<SchedMode>(initSched.mode);
  const [schedWeekly, setSchedWeekly]       = useState(initSched.weekly);
  const [schedHours, setSchedHours]         = useState(initSched.hours);
  const [schedTimes, setSchedTimes]         = useState<string[]>(initSched.times);
  const [schedDays, setSchedDays]           = useState<number[]>(initSched.days);
  const [schedImageMode, setSchedImageMode] = useState(initSched.imageMode);
  const [schedContentType, setSchedContentType] = useState(initSched.contentType);
  const [schedPillar, setSchedPillar]       = useState(initSched.pillar);
  const [savingSched, setSavingSched]       = useState(false);
  const [savedSched, setSavedSched]         = useState(false);

  // 排期用：内容类型 & 内容方向列表
  const [schedContentTypes, setSchedContentTypes] = useState<string[]>([]);
  const [schedPillars, setSchedPillars]           = useState<string[]>([]);

  const [deleting, setDeleting] = useState(false);

  const refreshAccount = useCallback(async () => {
    const acc = await api.accounts.get(account.id);
    setAccount(acc);
    setDisplayName(acc.display_name ?? "");
    setFeishuEdits({
      app_token: acc.feishu_app_token ?? "",
      table_id:  acc.feishu_table_id  ?? "",
    });
    if (acc.login_status === "logged_in") setPhase("done");
    setSchedEnabled(acc.auto_generate_enabled);
    const s = parseSched(acc.generate_schedule_json);
    setSchedMode(s.mode);
    setSchedWeekly(s.weekly); setSchedHours(s.hours);
    setSchedTimes(s.times);   setSchedDays(s.days);
    setSchedImageMode(s.imageMode);
    setSchedContentType(s.contentType);
    setSchedPillar(s.pillar);
  }, [account.id]);

  // 展开时加载内容类型和内容方向
  useEffect(() => {
    if (collapsed) return;
    api.topics.listTypes(account.id).then(types => {
      setSchedContentTypes(types.map((t: { name: string }) => t.name));
    }).catch(() => {});
    api.strategy.get(account.id).then(s => {
      const pillars = (s.content_pillars || []) as Array<{ name: string }>;
      setSchedPillars(pillars.map(p => p.name).filter(Boolean));
    }).catch(() => {});
  }, [collapsed, account.id]);

  useEffect(() => () => { stopRef.current = true; }, []);

  // 展开时拉日志，折叠时停止（MCP 按需启动，不轮询运行状态）
  useEffect(() => {
    if (collapsed) {
      if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null; }
      return;
    }
    const poll = () => {
      api.accounts.mcpLogs(account.id, 150)
        .then(r => setLogs(r.lines))
        .catch(() => {});
    };
    poll();
    pollTimerRef.current = setInterval(poll, 4000);
    return () => { if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null; } };
  }, [collapsed, account.id]);

  async function saveName() {
    setSavingName(true);
    try { await api.accounts.update(account.id, { display_name: displayName }); await refreshAccount(); }
    finally { setSavingName(false); }
  }


  async function verifyStatus() {
    setVerifying(true); setVerifyResult(null);
    try {
      const res = await api.accounts.verifyLogin(account.id);
      setVerifyResult(res);
      await refreshAccount();
    } catch (e: unknown) {
      setVerifyResult({ logged_in: false, error: (e instanceof Error ? e.message : String(e)) });
    } finally { setVerifying(false); }
  }

  async function saveFeishu() {
    setSavingFeishu(true);
    try {
      await api.accounts.update(account.id, {
        feishu_app_token: feishuEdits.app_token,
        feishu_table_id:  feishuEdits.table_id,
      });
      await refreshAccount();
    } finally { setSavingFeishu(false); }
  }

  async function feishuSetup() {
    setSetupingFeishu(true); setFeishuSetupMsg(null);
    try {
      const res = await api.accounts.feishuSetup(account.id, {
        app_token: feishuEdits.app_token || undefined,
        table_id:  feishuEdits.table_id  || undefined,
      });
      let msg = "✓ 飞书认证成功";
      if (res.app_token) msg += "，已创建表格";
      setFeishuSetupMsg(msg);
      await refreshAccount();
    } catch (e: unknown) {
      setFeishuSetupMsg("✗ " + (e instanceof Error ? e.message : String(e)));
    } finally { setSetupingFeishu(false); }
  }

  async function feishuTest() {
    setTestingFeishu(true); setFeishuTestResult(null);
    try {
      const res = await api.accounts.feishuTest(account.id);
      setFeishuTestResult(res);
    } catch (e: unknown) {
      setFeishuTestResult({ error: "✗ " + (e instanceof Error ? e.message : String(e)) });
    } finally { setTestingFeishu(false); }
  }

  async function saveSchedule() {
    setSavingSched(true); setSavedSched(false);
    try {
      const obj: Record<string, unknown> = { mode: schedMode };
      if (schedMode === "frequency") obj.weekly_count = schedWeekly;
      if (schedMode === "interval")  obj.interval_hours = schedHours;
      if (schedMode === "times")     { obj.times = schedTimes; obj.days = schedDays; }
      // 生成参数（"auto" 表示不指定，由系统自动决定）
      obj.image_mode   = schedImageMode !== "auto" ? schedImageMode : null;
      obj.content_type = schedContentType !== "auto" ? schedContentType : null;
      obj.pillar       = schedPillar !== "auto" ? schedPillar : null;
      await api.accounts.update(account.id, {
        auto_generate_enabled:  schedEnabled,
        generate_schedule_json: JSON.stringify(obj),
      });
      await refreshAccount();
      setSavedSched(true); setTimeout(() => setSavedSched(false), 2500);
    } catch (e: unknown) {
      alert("保存失败：" + (e instanceof Error ? e.message : String(e)));
    } finally { setSavingSched(false); }
  }

  async function startLogin() {
    stopRef.current = false;
    setPhase("starting"); setMsg("");
    try {
      await api.accounts.loginStart(account.id);
      setPhase("polling");
      setMsg("浏览器窗口已打开，请在窗口中扫码登录小红书…");
      startPolling(account.id);
    } catch (e: unknown) { setMsg((e as Error).message); setPhase("idle"); }
  }

  async function startPolling(id: number) {
    while (!stopRef.current) {
      try {
        const res = await api.accounts.loginStatus(id);
        if (res.logged_in) { handleSuccess(res.nickname); return; }
      } catch { /**/ }
      await sleep(2000);
    }
  }

  function handleSuccess(nickname?: string) {
    stopRef.current = true; setPhase("done");
    setMsg(nickname ? `登录成功，欢迎 ${nickname}` : "登录成功");
    refreshAccount();
  }

  async function logout() {
    await api.accounts.logout(account.id);
    setPhase("idle"); setQrImg(""); setMsg(""); refreshAccount();
  }

  async function handleDelete() {
    if (!confirm(`确定删除账号「${cardTitle}」？所有该账号的选题、策略、内容都会一起删除。`)) return;
    setDeleting(true);
    try { await onDelete(account.id); }
    finally { setDeleting(false); }
  }

  const isLoggedIn = account.login_status === "logged_in";
  const cardTitle  = account.display_name || account.nickname || `账号 ${account.id}`;
  const hasFeishuTable = !!(account.feishu_app_token && account.feishu_table_id);
  const feishuDirty =
    feishuEdits.app_token !== (account.feishu_app_token ?? "") ||
    feishuEdits.table_id  !== (account.feishu_table_id  ?? "");

  const schedSummary =
    !schedEnabled ? "关" :
    schedMode === "frequency" ? `${schedWeekly} 篇/周` :
    schedMode === "interval"  ? `每 ${schedHours}h` :
    schedMode === "times"     ? `${schedDays.length}天×${schedTimes.length}次` : "开";

  const statusPills: { label: string; value: string; active: boolean }[] = [
    { label: "小红书", value: isLoggedIn ? "已登录" : "未登录", active: isLoggedIn },
    { label: "飞书",    value: hasFeishuTable ? "已配置" : "未配置", active: hasFeishuTable },
    { label: "排期",    value: schedSummary, active: schedEnabled },
  ];

  return (
    <div className="rounded-lg overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>

      {/* 卡片标题 + 状态条 */}
      <div className="px-5 py-4 flex items-center gap-4 cursor-pointer select-none"
        style={{ borderBottom: collapsed ? "none" : "1px solid var(--border)" }}
        onClick={() => setCollapsed(v => !v)}>
        <div className="flex items-center gap-3 min-w-0 shrink-0">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
            style={{ background: "var(--accent)", color: "#fff" }}>
            {cardTitle.slice(0, 1).toUpperCase()}
          </div>
          <span className="font-medium truncate">{cardTitle}</span>
        </div>
        <div className="flex items-center gap-2 flex-1 flex-wrap justify-end">
          {statusPills.map(p => (
            <span key={p.label}
              className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full"
              style={{
                background: p.active ? "color-mix(in srgb, var(--success) 12%, transparent)" : "var(--background)",
                border: `1px solid ${p.active ? "color-mix(in srgb, var(--success) 40%, transparent)" : "var(--border)"}`,
                color: p.active ? "var(--success)" : "var(--muted)",
              }}>
              <span className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: p.active ? "var(--success)" : "var(--muted)" }} />
              <span style={{ color: "var(--muted)" }}>{p.label}</span>
              <span className="font-medium">{p.value}</span>
            </span>
          ))}
          <span className="text-xs ml-1" style={{ color: "var(--muted)" }}>{collapsed ? "▼" : "▲"}</span>
        </div>
      </div>

      {!collapsed && (
      <div className="p-5 space-y-5">

        <div className="grid lg:grid-cols-2 gap-5 items-stretch">

          {/* ── 左栏：小红书账号 ───────────────────────────────── */}
          <div className="rounded-lg p-4 flex flex-col gap-3"
            style={{ background: "var(--background)", border: "1px solid var(--border)" }}>

            {/* 操作日志（MCP 按需启动，日志记录最近一次操作） */}
            <div>
              <p className="text-xs font-medium mb-1.5" style={{ color: "var(--muted)" }}>运行日志</p>
              <div className="rounded overflow-y-auto overflow-x-hidden text-xs font-mono leading-relaxed p-3"
                style={{ background: "#0d1117", color: "#c9d1d9", border: "1px solid var(--border)", height: 360, wordBreak: "break-all" }}>
                {logs.length === 0
                  ? <span style={{ color: "#6e7681" }}>暂无日志…</span>
                  : logs.map((l, i) => <div key={i}>{l}</div>)}
              </div>
            </div>

            <div style={{ borderTop: "1px solid var(--border)" }} />

            {/* 登录区：根据状态分支 */}
            {isLoggedIn && phase !== "qr" && phase !== "polling" ? (
              // 已登录：紧凑摘要
              <div className="space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="text-sm font-medium flex-1">
                    <span style={{ color: "var(--success)" }}>● 已登录</span>
                    {account.nickname && <span style={{ color: "var(--muted)" }}> · {account.nickname}</span>}
                  </p>
                  <button onClick={verifyStatus} disabled={verifying}
                    className="text-xs px-3 py-1.5 rounded disabled:opacity-50 shrink-0"
                    style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                    {verifying ? "验证中…" : "重新验证"}
                  </button>
                  <button onClick={logout}
                    className="text-xs px-3 py-1.5 rounded shrink-0"
                    style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                    退出登录
                  </button>
                </div>
                {verifyResult !== null && (
                  <div className="text-xs px-3 py-2 rounded"
                    style={{
                      background: verifyResult.logged_in ? "#f0fdf4" : "#fff7ed",
                      border: `1px solid ${verifyResult.logged_in ? "#bbf7d0" : "#fed7aa"}`,
                      color: verifyResult.logged_in ? "var(--success)" : "var(--warning)",
                    }}>
                    {verifyResult.logged_in
                      ? `✓ 已登录${verifyResult.nickname ? `，账号：${verifyResult.nickname}` : ""}`
                      : `✗ ${verifyResult.error || "未登录，请先扫码登录"}`}
                  </div>
                )}
              </div>
            ) : phase === "starting" || phase === "polling" ? (
              // 等待扫码中
              <div className="space-y-3">
                <div className="flex items-center gap-2.5 px-3 py-3 rounded-lg"
                  style={{ background: "color-mix(in srgb, var(--accent) 8%, transparent)", border: "1px solid color-mix(in srgb, var(--accent) 20%, transparent)" }}>
                  <div className="w-4 h-4 rounded-full border-2 shrink-0 animate-spin"
                    style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
                  <p className="text-sm" style={{ color: "var(--foreground)" }}>
                    {phase === "starting" ? "正在启动浏览器…" : "请在弹出的浏览器窗口中扫码登录小红书"}
                  </p>
                </div>
                {phase === "polling" && (
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    扫码并在小红书 App 中确认后，页面会自动更新。
                  </p>
                )}
                <div className="text-center">
                  <button onClick={() => { stopRef.current = true; setPhase("idle"); setMsg(""); }}
                    className="text-xs" style={{ color: "var(--muted)" }}>取消</button>
                </div>
              </div>
            ) : (
              // 未登录：引导流程
              <div className="space-y-3">
                <p className="text-sm font-medium">小红书登录</p>
                <div className="flex gap-2 flex-wrap">
                  <button onClick={startLogin}
                    className="text-xs px-3 py-1.5 rounded"
                    style={{ background: "var(--accent)", color: "#fff" }}>
                    扫码登录小红书
                  </button>
                  <button onClick={verifyStatus} disabled={verifying}
                    className="text-xs px-3 py-1.5 rounded disabled:opacity-50"
                    style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                    {verifying ? "验证中…" : "验证登录状态"}
                  </button>
                </div>
                {msg && <p className="text-xs" style={{ color: "var(--muted)" }}>{msg}</p>}
                {verifyResult !== null && (
                  <div className="text-xs px-3 py-2 rounded"
                    style={{
                      background: verifyResult.logged_in ? "#f0fdf4" : "#fff7ed",
                      border: `1px solid ${verifyResult.logged_in ? "#bbf7d0" : "#fed7aa"}`,
                      color: verifyResult.logged_in ? "var(--success)" : "var(--warning)",
                    }}>
                    {verifyResult.logged_in
                      ? `✓ 已登录${verifyResult.nickname ? `，账号：${verifyResult.nickname}` : ""}`
                      : "✗ 验证失败，请检查 MCP 是否正常运行"}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* ── 右栏：飞书 + 排期 ─────────────────────────────── */}
          <div className="rounded-lg p-4 space-y-5"
            style={{ background: "var(--background)", border: "1px solid var(--border)" }}>

            {/* 飞书 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium" style={{ color: "var(--muted)" }}>飞书多维表格</p>
                {hasFeishuTable && (
                  <a href={`https://www.feishu.cn/base/${account.feishu_app_token}?table=${account.feishu_table_id}`}
                    target="_blank" rel="noreferrer"
                    className="text-xs px-2 py-0.5 rounded"
                    style={{ border: "1px solid var(--border)", color: "var(--accent)" }}>
                    打开 ↗
                  </a>
                )}
              </div>
              <div className="space-y-2">
                <input type="text" placeholder="App Token（/base/xxxx）"
                  value={feishuEdits.app_token}
                  onChange={e => setFeishuEdits(p => ({ ...p, app_token: e.target.value }))}
                  className={inputBase} style={inputStyle} />
                <input type="text" placeholder="Table ID（table=xxxx）"
                  value={feishuEdits.table_id}
                  onChange={e => setFeishuEdits(p => ({ ...p, table_id: e.target.value }))}
                  className={inputBase} style={inputStyle} />
              </div>
              <div className="flex gap-2 flex-wrap">
                <button onClick={feishuSetup} disabled={setupingFeishu || hasFeishuTable}
                  className="text-xs px-3 py-1.5 rounded disabled:opacity-50"
                  style={{ background: "var(--accent)", color: "#fff" }}>
                  {setupingFeishu ? "获取中…" : "获取飞书配置"}
                </button>
                <button onClick={saveFeishu} disabled={savingFeishu || !feishuDirty}
                  className="text-xs px-3 py-1.5 rounded disabled:opacity-50"
                  style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                  {savingFeishu ? "保存中…" : "手动保存"}
                </button>
                <button onClick={feishuTest} disabled={testingFeishu}
                  className="text-xs px-3 py-1.5 rounded disabled:opacity-50"
                  style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                  {testingFeishu ? "测试中…" : "连通性测试"}
                </button>
              </div>
              {feishuSetupMsg && (
                <p className="text-xs" style={{ color: feishuSetupMsg.startsWith("✓") ? "#22c55e" : "#ef4444" }}>
                  {feishuSetupMsg}
                </p>
              )}
              {feishuTestResult && (
                <div className="space-y-1 text-xs">
                  {Object.entries(feishuTestResult).map(([k, v]) => (
                    <p key={k} style={{ color: String(v).startsWith("✓") ? "#22c55e" : String(v).startsWith("—") ? "var(--muted)" : "#ef4444" }}>
                      {k === "table_write" ? "表格写入" : k === "table_delete" ? "表格删除" : k === "message" ? "消息发送" : k}：{v}
                    </p>
                  ))}
                </div>
              )}
            </div>

            {/* 排期 */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium" style={{ color: "var(--muted)" }}>自动生成排期</p>
                <div className="flex items-center gap-2">
                  <span className="text-xs" style={{ color: "var(--muted)" }}>{schedEnabled ? "已启用" : "已关闭"}</span>
                  <button onClick={() => setSchedEnabled(v => !v)}
                    className="relative shrink-0 rounded-full transition-colors"
                    style={{ width: 32, height: 18, background: schedEnabled ? "var(--accent)" : "var(--border)" }}>
                    <span className="absolute top-0.5 rounded-full transition-all"
                      style={{ width: 14, height: 14, background: "#fff", left: schedEnabled ? 16 : 2 }} />
                  </button>
                </div>
              </div>

              {schedEnabled && (
                <div className="space-y-3">
                  <div className="flex rounded overflow-hidden text-xs" style={{ border: "1px solid var(--border)" }}>
                    {([["frequency","随机分配"],["interval","固定间隔"],["times","指定时间"]] as [SchedMode,string][]).map(([m, label]) => (
                      <button key={m} onClick={() => setSchedMode(m)}
                        className="flex-1 py-1.5 transition-colors"
                        style={{
                          background: schedMode === m ? "var(--accent)" : "transparent",
                          color: schedMode === m ? "#fff" : "var(--muted)",
                          borderRight: m !== "times" ? "1px solid var(--border)" : undefined,
                        }}>
                        {label}
                      </button>
                    ))}
                  </div>

                  {schedMode === "frequency" && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs" style={{ color: "var(--muted)" }}>每周生成</span>
                      <input type="number" min={1} max={14} value={schedWeekly}
                        onChange={e => setSchedWeekly(Math.max(1, Math.min(14, parseInt(e.target.value) || 3)))}
                        className="w-14 text-sm px-2 py-1 rounded text-center" style={inputStyle} />
                      <span className="text-xs" style={{ color: "var(--muted)" }}>篇，随机分配时间</span>
                    </div>
                  )}

                  {schedMode === "interval" && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs" style={{ color: "var(--muted)" }}>每隔</span>
                      <input type="number" min={1} max={168} value={schedHours}
                        onChange={e => setSchedHours(Math.max(1, parseInt(e.target.value) || 8))}
                        className="w-14 text-sm px-2 py-1 rounded text-center" style={inputStyle} />
                      <span className="text-xs" style={{ color: "var(--muted)" }}>小时生成一次</span>
                    </div>
                  )}

                  {schedMode === "times" && (
                    <div className="space-y-2">
                      <div className="flex flex-wrap gap-1">
                        {PRESET_TIMES.map(t => (
                          <button key={t} onClick={() => setSchedTimes(prev => {
                            const has = prev.includes(t);
                            const next = has ? prev.filter(x => x !== t) : [...prev, t].sort();
                            return next.length ? next : [t];
                          })}
                            className="text-xs px-2 py-1 rounded transition-colors"
                            style={{
                              background: schedTimes.includes(t) ? "var(--accent)" : "var(--background)",
                              color: schedTimes.includes(t) ? "#fff" : "var(--muted)",
                              border: "1px solid var(--border)",
                            }}>
                            {t}
                          </button>
                        ))}
                      </div>
                      <div className="flex gap-1">
                        {DAY_LABELS.map((label, i) => (
                          <button key={i} onClick={() => setSchedDays(prev => {
                            const has = prev.includes(i);
                            const next = has ? prev.filter(x => x !== i) : [...prev, i].sort();
                            return next.length ? next : [i];
                          })}
                            className="text-xs rounded transition-colors"
                            style={{
                              width: 28, height: 28,
                              background: schedDays.includes(i) ? "var(--accent)" : "var(--background)",
                              color: schedDays.includes(i) ? "#fff" : "var(--muted)",
                              border: "1px solid var(--border)",
                            }}>
                            {label}
                          </button>
                        ))}
                      </div>
                      <p className="text-xs" style={{ color: "var(--muted)" }}>
                        每周 {schedDays.length} 天 × {schedTimes.length} 次 = {schedDays.length * schedTimes.length} 次
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* 生成参数配置 */}
              <div className="space-y-2 pt-1" style={{ borderTop: "1px solid var(--border)" }}>
                <p className="text-xs font-medium" style={{ color: "var(--muted)" }}>生成参数</p>

                {/* 图片模式 */}
                <div className="flex items-center gap-2">
                  <span className="text-xs shrink-0 w-16" style={{ color: "var(--muted)" }}>图片模式</span>
                  <div className="flex flex-wrap gap-1">
                    {[
                      { v: "random", label: "随机" },
                      { v: "cards",  label: "图文卡片" },
                      { v: "ai",     label: "AI 封面" },
                      { v: "both",   label: "封面+卡片" },
                    ].map(({ v, label }) => (
                      <button key={v} onClick={() => setSchedImageMode(v)}
                        className="text-xs px-2 py-1 rounded transition-colors"
                        style={{
                          background: schedImageMode === v ? "var(--accent)" : "var(--background)",
                          color: schedImageMode === v ? "#fff" : "var(--muted)",
                          border: "1px solid var(--border)",
                        }}>{label}</button>
                    ))}
                  </div>
                </div>

                {/* 内容类型 */}
                <div className="flex items-center gap-2">
                  <span className="text-xs shrink-0 w-16" style={{ color: "var(--muted)" }}>内容类型</span>
                  <div className="flex flex-wrap gap-1">
                    <button onClick={() => setSchedContentType("auto")}
                      className="text-xs px-2 py-1 rounded transition-colors"
                      style={{
                        background: schedContentType === "auto" ? "var(--accent)" : "var(--background)",
                        color: schedContentType === "auto" ? "#fff" : "var(--muted)",
                        border: "1px solid var(--border)",
                      }}>轮询</button>
                    {schedContentTypes.map(ct => (
                      <button key={ct} onClick={() => setSchedContentType(ct)}
                        className="text-xs px-2 py-1 rounded transition-colors"
                        style={{
                          background: schedContentType === ct ? "var(--accent)" : "var(--background)",
                          color: schedContentType === ct ? "#fff" : "var(--muted)",
                          border: "1px solid var(--border)",
                        }}>{ct}</button>
                    ))}
                  </div>
                </div>

                {/* 内容方向 */}
                {schedPillars.length > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs shrink-0 w-16" style={{ color: "var(--muted)" }}>内容方向</span>
                    <div className="flex flex-wrap gap-1">
                      <button onClick={() => setSchedPillar("auto")}
                        className="text-xs px-2 py-1 rounded transition-colors"
                        style={{
                          background: schedPillar === "auto" ? "var(--accent)" : "var(--background)",
                          color: schedPillar === "auto" ? "#fff" : "var(--muted)",
                          border: "1px solid var(--border)",
                        }}>自动</button>
                      {schedPillars.map(p => (
                        <button key={p} onClick={() => setSchedPillar(p)}
                          className="text-xs px-2 py-1 rounded transition-colors"
                          style={{
                            background: schedPillar === p ? "var(--accent)" : "var(--background)",
                            color: schedPillar === p ? "#fff" : "var(--muted)",
                            border: "1px solid var(--border)",
                          }}>{p}</button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <button onClick={saveSchedule} disabled={savingSched}
                className="text-xs px-4 py-1.5 rounded disabled:opacity-50"
                style={{ background: savedSched ? "#22c55e" : "var(--accent)", color: "#fff" }}>
                {savingSched ? "保存中…" : savedSched ? "✓ 已保存" : "保存排期"}
              </button>
            </div>
          </div>
        </div>

        {/* ── 底部：账号设置 ──────────────────────────────────── */}
        <div className="pt-4 flex items-center gap-3 flex-wrap"
          style={{ borderTop: "1px solid var(--border)" }}>
          <label className="text-xs font-medium shrink-0" style={{ color: "var(--muted)" }}>备注名</label>
          <input type="text" value={displayName} onChange={e => setDisplayName(e.target.value)}
            placeholder={account.nickname || "输入备注名…"}
            className="text-sm px-3 py-1.5 rounded flex-1 min-w-[200px]" style={inputStyle} />
          <button onClick={saveName} disabled={savingName}
            className="text-xs px-3 py-1.5 rounded disabled:opacity-40 shrink-0"
            style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
            {savingName ? "保存中…" : "保存"}
          </button>
          <button onClick={handleDelete} disabled={deleting}
            className="text-xs px-3 py-1.5 rounded disabled:opacity-50 shrink-0 ml-auto"
            style={{ border: "1px solid #ef444488", color: "#ef4444" }}>
            {deleting ? "删除中…" : "删除账号"}
          </button>
        </div>

      </div>
      )}
    </div>
  );
}

function sleep(ms: number) { return new Promise(r => setTimeout(r, ms)); }
