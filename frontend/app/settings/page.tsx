"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

type Section = "ai" | "feishu" | "publish" | "system" | "proxy";

// 飞书企业自建应用所需权限（仅保留 RedBeacon 实际用到的）
const FEISHU_REQUIRED_SCOPES = {
  tenant: [
    "bitable:app",
    "bitable:app:readonly",
    "base:app:copy",
    "base:app:create",
    "base:app:read",
    "base:app:update",
    "base:collaborator:create",
    "base:collaborator:read",
    "base:field:create",
    "base:field:read",
    "base:record:create",
    "base:record:delete",
    "base:record:read",
    "base:record:retrieve",
    "base:record:update",
    "base:table:create",
    "base:table:read",
    "base:view:read",
    "docs:permission.member:create",
    "docs:permission.member:readonly",
    "docs:permission.member:retrieve",
    "docs:permission.member:transfer",
    "drive:file",
    "drive:file:download",
    "drive:file:readonly",
    "drive:file:upload",
    "contact:user.base:readonly",
    "contact:user.id:readonly",
    "contact:user.employee_id:readonly",
    "im:message",
    "im:message:send_as_bot",
    "im:message:send_multi_users",
    "im:message:readonly",
    "im:resource",
  ],
  user: [
    "contact:user.employee_id:readonly",
  ],
};

const SENTINEL = "__SET__";

const inputBase = "w-full text-sm px-3 py-2 rounded outline-none";
const inputStyle = { background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" };

// ── 组件 ──────────────────────────────────────────────────────────────────────

function Field({
  label, fieldKey, secret, placeholder, hint, edits, isSet, onChange,
}: {
  label: string; fieldKey: string; secret?: boolean;
  placeholder?: string; hint?: string;
  edits: Record<string, string>;
  isSet: Record<string, boolean>;
  onChange: (key: string, val: string) => void;
}) {
  const val = edits[fieldKey] ?? "";
  const alreadySet = isSet[fieldKey] && val === "";

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium flex-1" style={{ color: "var(--muted)" }}>{label}</label>
        {alreadySet && (
          <span className="text-xs px-1.5 py-0.5 rounded"
            style={{ background: "#f0fdf4", color: "#16a34a", border: "1px solid #bbf7d0" }}>
            已设置
          </span>
        )}
      </div>
      <input
        type={secret ? "password" : "text"}
        value={val}
        onChange={e => onChange(fieldKey, e.target.value)}
        placeholder={alreadySet ? "••••••••（已设置，输入新值可覆盖）" : placeholder}
        className={inputBase}
        style={inputStyle}
      />
      {hint && <p className="text-xs" style={{ color: "var(--muted)" }}>{hint}</p>}
    </div>
  );
}

function ModelField({
  label, fieldKey, placeholder, edits, models, onChange,
}: {
  label: string; fieldKey: string; placeholder?: string;
  edits: Record<string, string>;
  models: string[];
  onChange: (key: string, val: string) => void;
}) {
  const current = edits[fieldKey] ?? "";
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium block" style={{ color: "var(--muted)" }}>{label}</label>
      <input
        type="text"
        value={current}
        onChange={e => onChange(fieldKey, e.target.value)}
        placeholder={placeholder}
        className={inputBase}
        style={inputStyle}
      />
      {models.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1">
          {models.map(m => (
            <button key={m} onClick={() => onChange(fieldKey, m)}
              className="text-xs px-2 py-0.5 rounded-full transition-colors"
              style={{
                background: current === m ? "var(--accent)" : "var(--background)",
                color: current === m ? "#fff" : "var(--muted)",
                border: `1px solid ${current === m ? "var(--accent)" : "var(--border)"}`,
              }}>
              {m}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!checked)}
      className="relative shrink-0 rounded-full transition-colors"
      style={{ width: 40, height: 22, background: checked ? "var(--accent)" : "var(--border)" }}>
      <span className="absolute top-0.5 rounded-full transition-all"
        style={{ width: 18, height: 18, background: "#fff", left: checked ? 20 : 2 }} />
    </button>
  );
}

function PickFileButton({ onPick }: { onPick: (path: string) => void }) {
  const [picking, setPicking] = useState(false);
  async function pick() {
    setPicking(true);
    try {
      const res = await api.settings.pickFile();
      if (res.path) onPick(res.path);
    } catch { /* ignore */ }
    finally { setPicking(false); }
  }
  return (
    <button onClick={pick} disabled={picking}
      className="shrink-0 text-xs px-3 py-2 rounded disabled:opacity-40 whitespace-nowrap"
      style={{ border: "1px solid var(--border)", color: "var(--foreground)", background: "var(--background)" }}>
      {picking ? "…" : "选择文件"}
    </button>
  );
}

function PickFolderButton({ onPick }: { onPick: (path: string) => void }) {
  const [picking, setPicking] = useState(false);
  async function pick() {
    setPicking(true);
    try {
      const res = await api.settings.pickFolder();
      if (res.path) onPick(res.path);
    } catch { /* ignore */ }
    finally { setPicking(false); }
  }
  return (
    <button onClick={pick} disabled={picking}
      className="shrink-0 text-xs px-3 py-2 rounded disabled:opacity-40 whitespace-nowrap"
      style={{ border: "1px solid var(--border)", color: "var(--foreground)", background: "var(--background)" }}>
      {picking ? "…" : "选择目录"}
    </button>
  );
}

function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      {children}
    </div>
  );
}

const FEISHU_OPEN_URL = "https://open.feishu.cn/app";

const GUIDE_STEPS = [
  { step: "1", title: "创建企业自建应用", desc: <>进入 <a href={FEISHU_OPEN_URL} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", textDecoration: "underline" }}>飞书开放平台</a>，点击「创建企业自建应用」，填写应用名称（如 RedBeacon）和描述。</> },
  { step: "2", title: "批量导入权限", desc: "进入应用 → 权限管理 → 点击「导入权限」→ 将下方 JSON 粘贴进去 → 确认导入，一键开通所有所需权限。" },
  { step: "3", title: "配置重定向 URL（可选）", desc: "如需用户授权登录，在「安全设置」中添加回调域名。纯机器人模式无需此步骤。" },
  { step: "4", title: "发布应用版本", desc: "进入「版本管理与发布」，创建并提交版本审核。自用企业可直接审核通过，审核通过后权限才会生效。" },
  { step: "5", title: "获取凭证", desc: "进入「凭证与基础信息」，复制 App ID 和 App Secret 填写到下方。" },
];

function FeishuGuideCard() {
  const [open, setOpen] = useState(false);
  const [jsonCopied, setJsonCopied] = useState(false);

  function copyJson() {
    navigator.clipboard.writeText(JSON.stringify(FEISHU_REQUIRED_SCOPES, null, 2)).then(() => {
      setJsonCopied(true);
      setTimeout(() => setJsonCopied(false), 2000);
    });
  }

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
      {/* 标题栏 */}
      <button onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-5 py-3.5"
        style={{ background: "var(--surface)" }}>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">企业自建应用配置指南</span>
          <span className="text-xs px-2 py-0.5 rounded-full"
            style={{ background: "color-mix(in srgb, var(--accent) 12%, transparent)", color: "var(--accent)" }}>
            首次配置必读
          </span>
        </div>
        <span className="text-xs" style={{ color: "var(--muted)" }}>{open ? "▲ 收起" : "▼ 展开"}</span>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-5" style={{ borderTop: "1px solid var(--border)", background: "var(--surface)" }}>

          {/* 步骤 */}
          <div className="space-y-3 pt-4">
            {GUIDE_STEPS.map(s => (
              <div key={s.step} className="flex gap-3">
                <div className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                  style={{ background: "var(--accent)", color: "#fff" }}>
                  {s.step}
                </div>
                <div>
                  <p className="text-sm font-medium">{s.title}</p>
                  <p className="text-xs mt-0.5 leading-relaxed" style={{ color: "var(--muted)" }}>{s.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* 权限列表 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">所需权限</p>
              <button onClick={copyJson}
                className="text-xs px-3 py-1.5 rounded transition-colors"
                style={{ background: jsonCopied ? "#22c55e" : "var(--accent)", color: "#fff" }}>
                {jsonCopied ? "✓ 已复制" : "复制 JSON"}
              </button>
            </div>

            <pre className="text-xs p-3 rounded-lg overflow-auto leading-relaxed font-mono"
              style={{ background: "var(--background)", border: "1px solid var(--border)", maxHeight: 280, color: "var(--foreground)" }}>
              {JSON.stringify(FEISHU_REQUIRED_SCOPES, null, 2)}
            </pre>

            <p className="text-xs" style={{ color: "var(--muted)" }}>
              ⚠️ 权限添加后需重新发布应用版本才能生效。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── 主页面 ────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [rawValues, setRawValues] = useState<Record<string, string>>({});
  const [edits, setEdits]         = useState<Record<string, string>>({});
  const [isSet, setIsSet]         = useState<Record<string, boolean>>({});
  const [section, setSection]     = useState<Section>("ai");

  const [models, setModels]               = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [testingAi, setTestingAi]         = useState(false);
  const [testAiResult, setTestAiResult]   = useState<string | null>(null);
  const [testingImg, setTestingImg]       = useState(false);
  const [testImgResult, setTestImgResult] = useState<string | null>(null);

  const [saving, setSaving] = useState<Section | null>(null);
  const [saved, setSaved]   = useState<Section | null>(null);

  const [testingFeishuAuth, setTestingFeishuAuth]     = useState(false);
  const [feishuAuthResult, setFeishuAuthResult]       = useState<string | null>(null);
  const [fetchingUsers, setFetchingUsers]             = useState(false);
  const [feishuUsers, setFeishuUsers]                 = useState<Array<{ user_id: string; name: string }> | null>(null);
  const [userFetchMsg, setUserFetchMsg]               = useState<string | null>(null);

  const [proxyTesting, setProxyTesting]               = useState(false);
  const [proxyTestResult, setProxyTestResult]         = useState<string | null>(null);

  useEffect(() => {
    api.settings.getAll().then(v => {
      const editVals: Record<string, string> = {};
      const setFlags: Record<string, boolean> = {};
      for (const [k, val] of Object.entries(v)) {
        if (val === SENTINEL) { editVals[k] = ""; setFlags[k] = true; }
        else { editVals[k] = val; setFlags[k] = false; }
      }
      setRawValues(v);
      setEdits(editVals);
      setIsSet(setFlags);
    });
  }, []);

  const onChange = useCallback((key: string, val: string) => {
    setEdits(prev => ({ ...prev, [key]: val }));
  }, []);

  const SECTION_KEYS: Record<Section, string[]> = {
    ai:      ["ai_api_key", "ai_base_url", "ai_model", "image_model"],
    feishu:  ["feishu_app_id", "feishu_app_secret", "feishu_user_id"],
    publish: ["publish_is_original", "publish_is_ai_generated", "publish_visibility"],
    system:  ["mcp_tools_dir", "mcp_visible"],
    proxy:   ["proxy_api_url", "proxy_auto_rotate", "proxy_speed_test"],
  };

  const isSectionDirty = (sec: Section) =>
    SECTION_KEYS[sec].some(k => {
      const cur  = edits[k] ?? "";
      const orig = rawValues[k] === SENTINEL ? "" : (rawValues[k] ?? "");
      return cur !== orig && !(cur === "" && isSet[k]);
    });

  async function saveSection(sec: Section) {
    setSaving(sec);
    try {
      const items = SECTION_KEYS[sec].map(key => ({ key, value: edits[key] ?? "" }))
        .filter(item => !(item.value === "" && isSet[item.key]));
      await api.settings.batch(items);
      const updated: Record<string, string> = {};
      items.forEach(i => { updated[i.key] = i.value; });
      setRawValues(prev => ({ ...prev, ...updated }));
      for (const item of items) {
        if (item.value && ["ai_api_key", "feishu_app_secret"].includes(item.key)) {
          setIsSet(prev => ({ ...prev, [item.key]: true }));
          setEdits(prev => ({ ...prev, [item.key]: "" }));
        }
      }
      setSaved(sec);
      setTimeout(() => setSaved(null), 2500);
    } finally { setSaving(null); }
  }

  async function fetchModels() {
    setLoadingModels(true); setModels([]);
    try {
      const res = await api.settings.models();
      setModels(res.models);
      if (res.models.length === 0)
        alert(`没有获取到模型\nraw_keys: ${JSON.stringify(res.raw_keys)}\nraw: ${JSON.stringify(res.raw)}`);
    } catch (e: unknown) {
      alert("获取失败：" + (e instanceof Error ? e.message : String(e)));
    } finally { setLoadingModels(false); }
  }

  async function testAi() {
    setTestingAi(true); setTestAiResult(null);
    try {
      const res = await api.settings.testAi();
      setTestAiResult(`✓ 模型 ${res.model} 回复：${res.reply}`);
    } catch (e: unknown) {
      setTestAiResult("✗ " + (e instanceof Error ? e.message : String(e)));
    } finally { setTestingAi(false); }
  }

  async function testImage() {
    setTestingImg(true); setTestImgResult(null);
    try {
      const res = await api.settings.testImage();
      setTestImgResult(res.found_in_list ? `✓ 模型 ${res.model} 可用` : `⚠ 连通但未找到模型 ${res.model}`);
    } catch (e: unknown) {
      setTestImgResult("✗ " + (e instanceof Error ? e.message : String(e)));
    } finally { setTestingImg(false); }
  }

  async function fetchFeishuUsers() {
    setFetchingUsers(true); setFeishuUsers(null); setUserFetchMsg(null);
    try {
      if (isSectionDirty("feishu")) await saveSection("feishu");
      const res = await api.settings.feishuUsers();
      if (res.users.length === 0) {
        setUserFetchMsg("未找到成员（请确认应用已开通 contact:user:readonly 权限）");
      } else {
        setFeishuUsers(res.users);
      }
    } catch (e: unknown) {
      setUserFetchMsg("✗ " + (e instanceof Error ? e.message : String(e)));
    } finally { setFetchingUsers(false); }
  }

  async function testFeishuAuth() {
    setTestingFeishuAuth(true); setFeishuAuthResult(null);
    try {
      if (isSectionDirty("feishu")) await saveSection("feishu");
      const res = await api.settings.testFeishuAuth();
      setFeishuAuthResult(res.msg);
    } catch (e: unknown) {
      setFeishuAuthResult("✗ " + (e instanceof Error ? e.message : String(e)));
    } finally { setTestingFeishuAuth(false); }
  }

  async function testProxy() {
    setProxyTesting(true); setProxyTestResult(null);
    try {
      if (isSectionDirty("proxy")) await saveSection("proxy");
      const res = await api.settings.proxyTest();
      setProxyTestResult(`✓ 接口正常，获取到 IP：${res.proxy}`);
    } catch (e: unknown) {
      setProxyTestResult("✗ " + (e instanceof Error ? e.message : String(e)));
    } finally { setProxyTesting(false); }
  }

  const TABS: { id: Section; label: string }[] = [
    { id: "ai",      label: "AI 模型"  },
    { id: "feishu",  label: "飞书配置" },
    { id: "publish", label: "发布设置" },
    { id: "proxy",   label: "代理设置" },
    { id: "system",  label: "MCP 配置" },
  ];

  const fp = { edits, isSet, onChange };
  const mp = { edits, models, onChange };

  const SaveBtn = ({ sec }: { sec: Section }) => (
    <button onClick={() => saveSection(sec)} disabled={saving === sec || !isSectionDirty(sec)}
      className="px-6 py-2 rounded text-sm disabled:opacity-40"
      style={{ background: saved === sec ? "#22c55e" : "var(--accent)", color: "#fff" }}>
      {saving === sec ? "保存中…" : saved === sec ? "✓ 已保存" : "保存"}
    </button>
  );

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">设置</h1>

      <div className="flex gap-6 items-start">

        {/* ── 侧边栏 Tab ─────────────────────────────────────────────────── */}
        <div className="w-36 shrink-0 rounded-lg overflow-hidden"
          style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
          {TABS.map((t, i) => (
            <button key={t.id} onClick={() => setSection(t.id)}
              className="w-full text-left text-sm py-3 px-4 transition-colors"
              style={{
                background: section === t.id ? "var(--accent)" : "transparent",
                color: section === t.id ? "#fff" : "var(--muted)",
                borderBottom: i < TABS.length - 1 ? "1px solid var(--border)" : "none",
              }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── 内容区 ─────────────────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 space-y-4">

          {/* AI 模型 */}
          {section === "ai" && (
            <>
              <SectionCard>
                <div className="space-y-4">
                  <Field label="AI API Key" fieldKey="ai_api_key" secret placeholder="sk-…" {...fp} />
                  <Field label="API Base URL" fieldKey="ai_base_url" placeholder="https://api.openai.com/v1" {...fp} />
                  <div className="flex gap-2 flex-wrap">
                    <button onClick={fetchModels} disabled={loadingModels}
                      className="text-xs px-3 py-1.5 rounded disabled:opacity-40"
                      style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                      {loadingModels ? "获取中…" : "获取模型列表"}
                    </button>
                  </div>
                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }} className="space-y-4">
                    <ModelField label="文案模型" fieldKey="ai_model" placeholder="输入或从列表选择" {...mp} />
                    <div className="flex gap-2 flex-wrap">
                      <button onClick={testAi} disabled={testingAi}
                        className="text-xs px-3 py-1.5 rounded disabled:opacity-40"
                        style={{ background: "var(--accent)", color: "#fff" }}>
                        {testingAi ? "测试中…" : "连通性测试"}
                      </button>
                    </div>
                    {testAiResult && (
                      <p className="text-xs" style={{ color: testAiResult.startsWith("✓") ? "#22c55e" : "#ef4444" }}>
                        {testAiResult}
                      </p>
                    )}
                  </div>
                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }} className="space-y-4">
                    <ModelField label="图片生成模型" fieldKey="image_model"
                      placeholder="例：gemini-2.0-flash-preview-image-generation" {...mp} />
                    <div className="flex gap-2 flex-wrap">
                      <button onClick={testImage} disabled={testingImg}
                        className="text-xs px-3 py-1.5 rounded disabled:opacity-40"
                        style={{ background: "var(--accent)", color: "#fff" }}>
                        {testingImg ? "测试中…" : "连通性测试"}
                      </button>
                    </div>
                    {testImgResult && (
                      <p className="text-xs" style={{
                        color: testImgResult.startsWith("✓") ? "#22c55e"
                          : testImgResult.startsWith("⚠") ? "#f59e0b" : "#ef4444"
                      }}>
                        {testImgResult}
                      </p>
                    )}
                  </div>
                </div>
              </SectionCard>
              <div className="flex justify-end"><SaveBtn sec="ai" /></div>
            </>
          )}

          {/* 飞书 */}
          {section === "feishu" && (
            <>
              <FeishuGuideCard />
              <SectionCard>
                <div className="space-y-4">
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    填写飞书应用凭证，供所有账号共用。每个账号的多维表格配置在「账号管理」中单独设置。
                  </p>
                  <Field label="App ID" fieldKey="feishu_app_id" placeholder="cli_…" {...fp} />
                  <Field label="App Secret" fieldKey="feishu_app_secret" secret placeholder="…" {...fp} />
                  <div className="space-y-2">
                    <Field label="接收通知的 User ID" fieldKey="feishu_user_id" placeholder="如 a1b2c3d4（飞书用户 ID，非 open_id）"
                      hint="所有账号发布通知统一发送到此 ID" {...fp} />
                    <div className="flex gap-2 flex-wrap">
                      <button onClick={fetchFeishuUsers} disabled={fetchingUsers}
                        className="text-xs px-3 py-1.5 rounded disabled:opacity-40"
                        style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                        {fetchingUsers ? "获取中…" : "获取 User ID"}
                      </button>
                    </div>
                    {userFetchMsg && (
                      <p className="text-xs" style={{ color: userFetchMsg.startsWith("✗") ? "#ef4444" : "var(--muted)" }}>
                        {userFetchMsg}
                      </p>
                    )}
                    {feishuUsers && feishuUsers.length > 0 && (
                      <div className="space-y-1">
                        {feishuUsers.map(u => (
                          <button key={u.user_id}
                            onClick={() => { onChange("feishu_user_id", u.user_id); setFeishuUsers(null); }}
                            className="w-full text-left text-xs px-3 py-2 rounded transition-colors"
                            style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" }}>
                            <span className="font-medium">{u.name}</span>
                            <span className="ml-2" style={{ color: "var(--muted)" }}>{u.user_id}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 items-center pt-1" style={{ borderTop: "1px solid var(--border)" }}>
                    <button onClick={testFeishuAuth} disabled={testingFeishuAuth}
                      className="text-xs px-3 py-1.5 rounded disabled:opacity-40"
                      style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                      {testingFeishuAuth ? "验证中…" : "验证凭证"}
                    </button>
                    <span className="text-xs" style={{ color: "var(--muted)" }}>验证 App ID / Secret 是否有效</span>
                  </div>
                  {feishuAuthResult && (
                    <p className="text-xs" style={{ color: feishuAuthResult.startsWith("✓") ? "#22c55e" : "#ef4444" }}>
                      {feishuAuthResult}
                    </p>
                  )}
                </div>
              </SectionCard>
              <div className="flex justify-end"><SaveBtn sec="feishu" /></div>
            </>
          )}

          {/* 发布设置 */}
          {section === "publish" && (
            <>
              <SectionCard>
                <div className="space-y-5">
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    每次发布笔记时使用这些默认参数。
                  </p>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm">声明原创</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>发布时标注为原创内容</p>
                    </div>
                    <Toggle
                      checked={(edits.publish_is_original ?? "false") === "true"}
                      onChange={v => onChange("publish_is_original", v ? "true" : "false")}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm">标注 AI 合成</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>声明内容含 AI 生成</p>
                    </div>
                    <Toggle
                      checked={(edits.publish_is_ai_generated ?? "true") === "true"}
                      onChange={v => onChange("publish_is_ai_generated", v ? "true" : "false")}
                    />
                  </div>
                  <div style={{ borderTop: "1px solid var(--border)", paddingTop: 16 }} className="space-y-3">
                    <p className="text-sm font-medium">可见范围</p>
                    <div className="space-y-2">
                      {["公开可见", "仅互关好友可见", "仅自己可见"].map(opt => (
                        <button key={opt} onClick={() => onChange("publish_visibility", opt)}
                          className="w-full text-left text-sm px-4 py-2.5 rounded transition-colors"
                          style={{
                            background: (edits.publish_visibility ?? "公开可见") === opt ? "var(--accent)" : "var(--background)",
                            color: (edits.publish_visibility ?? "公开可见") === opt ? "#fff" : "var(--foreground)",
                            border: `1px solid ${(edits.publish_visibility ?? "公开可见") === opt ? "var(--accent)" : "var(--border)"}`,
                          }}>
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </SectionCard>
              <div className="flex justify-end"><SaveBtn sec="publish" /></div>
            </>
          )}

          {/* 代理设置 */}
          {section === "proxy" && (
            <>
              <SectionCard>
                <div className="space-y-4">
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    每次发布任务触发时，系统自动调用此接口拉取一个新 IP，
                    重启 MCP 浏览器后再发布。IP 用完即弃，不做持久化存储。
                  </p>
                  <Field
                    label="代理 API URL"
                    fieldKey="proxy_api_url"
                    placeholder="https://v2.api.juliangip.com/...?num=1&result_type=json&..."
                    hint="每次调用返回 1 个 IP 即可；支持聚量、快代理等标准 JSON 格式"
                    {...fp}
                  />
                  <div className="flex items-center justify-between pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                    <div>
                      <p className="text-sm">发布前自动换 IP</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                        每次发布前拉取新 IP 并重启 MCP（约 3–5 秒）。关闭则直连发布。
                      </p>
                    </div>
                    <Toggle
                      checked={(edits.proxy_auto_rotate ?? "false") === "true"}
                      onChange={v => onChange("proxy_auto_rotate", v ? "true" : "false")}
                    />
                  </div>
                  <div className="flex items-center justify-between pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                    <div>
                      <p className="text-sm">换 IP 前测速过滤劣质代理</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                        开启后每次换 IP 前向小红书发一次探测请求（8 秒内无响应视为劣质），最多尝试 3 个 IP，全部不达标则不挂代理发布。
                      </p>
                    </div>
                    <Toggle
                      checked={(edits.proxy_speed_test ?? "false") === "true"}
                      onChange={v => onChange("proxy_speed_test", v ? "true" : "false")}
                    />
                  </div>
                  <div className="flex items-center gap-3 pt-1" style={{ borderTop: "1px solid var(--border)" }}>
                    <button
                      onClick={testProxy}
                      disabled={proxyTesting}
                      className="text-xs px-3 py-1.5 rounded disabled:opacity-40"
                      style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                      {proxyTesting ? "测试中…" : "测试接口"}
                    </button>
                    <span className="text-xs" style={{ color: "var(--muted)" }}>验证 API URL 能否成功取到 IP</span>
                  </div>
                  {proxyTestResult && (
                    <p className="text-xs" style={{ color: proxyTestResult.startsWith("✓") ? "#22c55e" : "#ef4444" }}>
                      {proxyTestResult}
                    </p>
                  )}
                </div>
              </SectionCard>
              <div className="flex justify-end"><SaveBtn sec="proxy" /></div>
            </>
          )}

          {/* 系统 */}
          {section === "system" && (
            <>
              <SectionCard>
                <div className="space-y-4">
                  <p className="text-xs" style={{ color: "var(--muted)" }}>
                    留空时自动从 <code className="mx-1 px-1 rounded" style={{ background: "var(--border)" }}>tools/</code> 目录查找，
                    无需手动填写。仅在工具放在非默认位置时才需要配置。
                  </p>
                  <div className="space-y-1">
                    <label className="text-xs font-medium block" style={{ color: "var(--muted)" }}>
                      工具目录
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={edits.mcp_tools_dir ?? ""}
                        onChange={e => onChange("mcp_tools_dir", e.target.value)}
                        placeholder="留空自动查找 redbeacon/tools/"
                        className={`${inputBase} flex-1`}
                        style={inputStyle}
                      />
                      <PickFolderButton onPick={path => onChange("mcp_tools_dir", path)} />
                    </div>
                    <p className="text-xs" style={{ color: "var(--muted)" }}>
                      选择包含 <code style={{ background: "var(--border)", padding: "0 4px", borderRadius: 3 }}>xiaohongshu-mcp</code> 和 <code style={{ background: "var(--border)", padding: "0 4px", borderRadius: 3 }}>xiaohongshu-login</code> 的目录，系统自动匹配对应平台的工具。
                    </p>
                  </div>
                  <div className="flex items-center justify-between pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                    <div>
                      <p className="text-sm">执行任务时显示浏览器窗口</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                        开启后发布、验证登录时浏览器可见，方便调试观察；生产环境建议关闭。
                      </p>
                    </div>
                    <Toggle
                      checked={(edits.mcp_visible ?? "false") === "true"}
                      onChange={v => onChange("mcp_visible", v ? "true" : "false")}
                    />
                  </div>

                  <div className="rounded-lg px-4 py-3 text-xs space-y-1"
                    style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                    <p className="font-medium">tools/ 目录应包含以下文件：</p>
                    <p style={{ color: "var(--muted)" }}>
                      <code>xiaohongshu-mcp</code>（macOS）／<code>xiaohongshu-mcp.exe</code>（Windows）— MCP 服务进程
                    </p>
                    <p style={{ color: "var(--muted)" }}>
                      <code>xiaohongshu-login</code>（macOS）／<code>xiaohongshu-login.exe</code>（Windows）— 扫码登录工具
                    </p>
                    <p style={{ color: "var(--muted)" }}>登录工具和 MCP 需放在同一目录，登录完成后自动切换到 MCP 服务模式。</p>
                  </div>
                </div>
              </SectionCard>
              <div className="flex justify-end"><SaveBtn sec="system" /></div>
            </>
          )}

        </div>
      </div>
    </div>
  );
}
