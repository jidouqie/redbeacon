"use client";

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { api, Account, ContentType, ImageTemplate } from "@/lib/api";

// ── 样式 ──────────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  color: "var(--foreground)",
  outline: "none",
};

type Tab = "copy" | "image";

// ── 账号策略数据（用于渲染变量实际值）─────────────────────────────────────────

interface StrategyData {
  niche: string;
  target_audience: string;
  tone: string;
  competitive_advantage: string;
  opening_style: string;
  format_style: string;
  emoji_usage: string;
  content_length: string;
  pain_points: string[];
  forbidden_words: string[];
  content_pillars: Array<{ name: string; description?: string }>;
}

function emptyStrategy(): StrategyData {
  return {
    niche: "", target_audience: "", tone: "", competitive_advantage: "",
    opening_style: "", format_style: "", emoji_usage: "", content_length: "",
    pain_points: [], forbidden_words: [], content_pillars: [],
  };
}

// ── 可用变量表（带实际值渲染）─────────────────────────────────────────────────

function VarTable({
  strategy, mode, topic, contentType, imageTitle,
}: {
  strategy: StrategyData;
  mode: "copy" | "image";
  topic?: string;
  contentType?: string;
  imageTitle?: string;
}) {
  const pillarText = strategy.content_pillars
    .filter(p => p.name)
    .map(p => p.name + (p.description ? `（${p.description}）` : ""))
    .join("、");

  const copyVars = [
    { key: "{niche}",                desc: "账号方向",   val: strategy.niche,                    filled: false },
    { key: "{target_audience}",      desc: "目标受众",   val: strategy.target_audience,           filled: false },
    { key: "{topic}",                desc: "选题",       val: topic || "",                        filled: true  },
    { key: "{content_type}",         desc: "内容类型",   val: contentType || "",                  filled: true  },
    { key: "{tone}",                 desc: "语气风格",   val: strategy.tone,                      filled: false },
    { key: "{competitive_advantage}", desc: "差异化优势", val: strategy.competitive_advantage,    filled: false },
    { key: "{opening_style}",        desc: "开场方式",   val: strategy.opening_style,             filled: false },
    { key: "{format_style}",         desc: "行文格式",   val: strategy.format_style,              filled: false },
    { key: "{emoji_usage}",          desc: "Emoji 用量", val: strategy.emoji_usage,               filled: false },
    { key: "{content_length}",       desc: "正文字数",   val: strategy.content_length,            filled: false },
    { key: "{pain_points}",          desc: "受众痛点",   val: strategy.pain_points.join(" / "),   filled: false },
    { key: "{forbidden_words}",      desc: "禁止词汇",   val: strategy.forbidden_words.join(" "),  filled: false },
    { key: "{content_pillars}",      desc: "内容方向",   val: pillarText,                         filled: false },
  ];

  const imageVars = [
    { key: "{niche}",  desc: "账号方向", val: strategy.niche,  filled: false },
    { key: "{title}",  desc: "文案标题", val: imageTitle || "", filled: true  },
  ];

  const vars = mode === "copy" ? copyVars : imageVars;

  return (
    <div className="rounded text-xs overflow-hidden"
      style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
      <div className="px-3 py-1.5 font-semibold"
        style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>
        可用变量
      </div>
      <table className="w-full">
        <tbody>
          {vars.map(v => (
            <tr key={v.key} style={{ borderBottom: "1px solid var(--border)" }}>
              <td className="px-3 py-1 w-36 font-mono whitespace-nowrap">
                <code style={{ color: "var(--accent)" }}>{v.key}</code>
              </td>
              <td className="px-3 py-1 w-20 whitespace-nowrap" style={{ color: "var(--muted)" }}>
                {v.desc}
              </td>
              <td className="px-3 py-1 truncate max-w-0">
                {v.val
                  ? <span style={{ color: v.filled ? "var(--accent)" : "var(--foreground)" }}>{v.val}</span>
                  : <span style={{ color: "var(--muted)", fontStyle: "italic" }}>
                      {v.filled ? "待填写" : "未设置"}
                    </span>
                }
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 账号选择器 ────────────────────────────────────────────────────────────────

function AccountSelector({
  accounts, value, onChange,
}: {
  accounts: Account[]; value: number; onChange: (id: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium whitespace-nowrap" style={{ color: "var(--muted)" }}>账号</span>
      <div className="flex gap-2 flex-wrap">
        {accounts.map(a => (
          <button key={a.id} onClick={() => onChange(a.id)}
            className="text-xs px-3 py-1.5 rounded transition-colors"
            style={{
              background: value === a.id ? "color-mix(in srgb, var(--accent) 12%, var(--background))" : "var(--surface)",
              border: `1px solid ${value === a.id ? "var(--accent)" : "var(--border)"}`,
              color: value === a.id ? "var(--accent)" : "var(--foreground)",
            }}>
            {a.display_name || a.nickname || `账号 ${a.id}`}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── 文案调试 tab ──────────────────────────────────────────────────────────────

function CopyDebugTab({
  accountId, strategy,
}: {
  accountId: number; strategy: StrategyData;
}) {
  const [topic, setTopic]               = useState("");
  const [unusedTopics, setUnusedTopics] = useState<string[]>([]);
  const [topicIdx, setTopicIdx]         = useState(0);
  const [contentType, setContentType]   = useState("");
  const [contentTypes, setContentTypes] = useState<ContentType[]>([]);
  const [template, setTemplate]         = useState("");
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [result, setResult]             = useState<{ title: string; body: string; tags: string[]; filled_prompt: string } | null>(null);
  const [showPrompt, setShowPrompt]     = useState(false);
  const [applying, setApplying]         = useState(false);
  const [applyMsg, setApplyMsg]         = useState("");
  const [previewOpen, setPreviewOpen]   = useState(true);

  // 实时计算填充后的完整 Prompt（镜像后端替换逻辑）
  const filledPrompt = useMemo(() => {
    if (!template) return "";
    const pillars = strategy.content_pillars
      .filter(p => p.name)
      .map(p => p.name + (p.description ? `（${p.description}）` : ""))
      .join("、");
    return template
      .replaceAll("{niche}",                strategy.niche)
      .replaceAll("{target_audience}",      strategy.target_audience)
      .replaceAll("{content_type}",         contentType || "（未选择）")
      .replaceAll("{topic}",                topic || "（未填写）")
      .replaceAll("{tone}",                 strategy.tone)
      .replaceAll("{competitive_advantage}", strategy.competitive_advantage)
      .replaceAll("{opening_style}",        strategy.opening_style)
      .replaceAll("{format_style}",         strategy.format_style)
      .replaceAll("{emoji_usage}",          strategy.emoji_usage)
      .replaceAll("{content_length}",       strategy.content_length)
      .replaceAll("{pain_points}",          strategy.pain_points.join(" / "))
      .replaceAll("{forbidden_words}",      strategy.forbidden_words.join(" "))
      .replaceAll("{content_pillars}",      pillars);
  }, [template, topic, contentType, strategy]);

  // 账号切换：加载内容类型列表 + 未用选题
  useEffect(() => {
    setResult(null);
    setApplyMsg("");

    api.topics.list(accountId, undefined, 0).then(topics => {
      const list = topics.map(t => t.content);
      setUnusedTopics(list);
      setTopicIdx(0);
      setTopic(list[0] ?? "");
    }).catch(() => {});

    api.topics.listTypes(accountId).then(types => {
      const active = types.filter(t => t.is_active);
      setContentTypes(active);
      const first = active[0];
      setContentType(first?.name ?? "");
      setTemplate(first?.prompt_template ?? "");
    }).catch(() => {});
  }, [accountId]);

  // 切换内容类型时更新提示词
  function selectContentType(name: string) {
    setContentType(name);
    const found = contentTypes.find(t => t.name === name);
    if (found) setTemplate(found.prompt_template);
  }

  function swapTopic() {
    if (unusedTopics.length === 0) return;
    const next = (topicIdx + 1) % unusedTopics.length;
    setTopicIdx(next);
    setTopic(unusedTopics[next]);
  }

  async function run() {
    if (!topic.trim()) { setError("请填写选题"); return; }
    if (!template.trim()) { setError("请填写提示词模板"); return; }
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const res = await api.debug.copy({ account_id: accountId, topic: topic.trim(), content_type: contentType.trim(), prompt_template: template });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  }

  async function applyToPreset() {
    if (!template.trim()) return;
    const found = contentTypes.find(t => t.name === contentType);
    if (!found) { setApplyMsg("请先选择一个内容类型"); setTimeout(() => setApplyMsg(""), 2000); return; }
    setApplying(true);
    setApplyMsg("");
    try {
      await api.topics.updateType(accountId, found.id, { prompt_template: template });
      // 从服务端重新拉取，保证按钮组和 selectContentType 切换时用的都是最新数据
      const fresh = await api.topics.listTypes(accountId);
      setContentTypes(fresh.filter(t => t.is_active));
      setApplyMsg(`已保存到「${found.name}」的文案预设`);
    } catch (e) {
      setApplyMsg("保存失败：" + (e instanceof Error ? e.message : "未知错误"));
    } finally {
      setApplying(false);
      setTimeout(() => setApplyMsg(""), 3000);
    }
  }

  return (
    <div className="grid grid-cols-2 gap-6 items-start">

      {/* 左：配置 */}
      <div className="space-y-4">

        {/* 选题：从选题库取，可换 */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted)" }}>
              选题
              {unusedTopics.length > 0 && (
                <span className="ml-1.5 font-normal" style={{ color: "var(--muted)" }}>
                  （未用 {unusedTopics.length} 条）
                </span>
              )}
            </label>
            {unusedTopics.length > 1 && (
              <button onClick={swapTopic}
                className="text-xs px-2 py-0.5 rounded"
                style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                换一个
              </button>
            )}
          </div>
          <input value={topic} onChange={e => setTopic(e.target.value)}
            placeholder="选题库为空时可手动输入"
            className="w-full text-sm px-3 py-2 rounded" style={inputStyle} />
        </div>

        {/* 内容类型：按钮组 */}
        <div>
          <label className="block text-xs mb-1.5 font-medium" style={{ color: "var(--muted)" }}>内容类型</label>
          {contentTypes.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {contentTypes.map(ct => (
                <button key={ct.name} onClick={() => selectContentType(ct.name)}
                  className="text-xs px-3 py-1.5 rounded transition-colors"
                  style={{
                    background: contentType === ct.name ? "color-mix(in srgb, var(--accent) 12%, var(--background))" : "var(--surface)",
                    border: `1px solid ${contentType === ct.name ? "var(--accent)" : "var(--border)"}`,
                    color: contentType === ct.name ? "var(--accent)" : "var(--foreground)",
                  }}>
                  {ct.name}
                </button>
              ))}
            </div>
          ) : (
            <input value={contentType} onChange={e => setContentType(e.target.value)}
              placeholder="例如：干货科普"
              className="w-full text-sm px-3 py-2 rounded" style={inputStyle} />
          )}
        </div>

        <VarTable strategy={strategy} mode="copy" topic={topic} contentType={contentType} />

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted)" }}>
              提示词模板
              {contentType && (
                <span className="ml-2 font-normal" style={{ color: "var(--accent)" }}>
                  · {contentType}
                </span>
              )}
            </label>
          </div>
          <textarea value={template} onChange={e => setTemplate(e.target.value)}
            rows={14} className="w-full text-xs px-3 py-2.5 rounded resize-y font-mono leading-relaxed"
            style={inputStyle} />
        </div>

        {/* 实际运行 Prompt 预览 */}
        <div className="rounded overflow-hidden" style={{ border: "1px solid var(--border)" }}>
          <button onClick={() => setPreviewOpen(v => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium"
            style={{ background: "var(--background)", color: "var(--muted)" }}>
            <span>实际运行的 Prompt</span>
            <span>{previewOpen ? "▲" : "▼"}</span>
          </button>
          {previewOpen && (
            <pre className="text-xs px-3 py-3 whitespace-pre-wrap leading-relaxed overflow-auto font-mono"
              style={{ background: "var(--background)", color: "var(--foreground)", maxHeight: 300, borderTop: "1px solid var(--border)" }}>
              {filledPrompt || <span style={{ color: "var(--muted)", fontStyle: "italic" }}>填写选题和模板后自动渲染…</span>}
            </pre>
          )}
        </div>

        {error && (
          <p className="text-xs px-3 py-2 rounded"
            style={{ background: "color-mix(in srgb,#ef4444 10%,transparent)", color: "#ef4444", border: "1px solid color-mix(in srgb,#ef4444 25%,transparent)" }}>
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button onClick={run} disabled={loading}
            className="flex-1 py-2.5 rounded text-sm font-medium disabled:opacity-50"
            style={{ background: "var(--accent)", color: "#fff" }}>
            {loading ? "生成中…" : "▶ 生成预览"}
          </button>
          <button onClick={applyToPreset} disabled={applying || !template.trim()}
            className="py-2.5 px-4 rounded text-sm disabled:opacity-40"
            style={{ border: "1px solid var(--border)", color: "var(--foreground)", whiteSpace: "nowrap" }}>
            {applying ? "保存中…" : "应用到文案预设"}
          </button>
        </div>
        {applyMsg && (
          <p className="text-xs" style={{ color: "var(--accent)" }}>{applyMsg}</p>
        )}
      </div>

      {/* 右：结果 */}
      <div className="space-y-4">
        {!result && !loading && (
          <div className="flex items-center justify-center rounded-lg"
            style={{ height: 320, background: "var(--surface)", border: "1px dashed var(--border)", color: "var(--muted)" }}>
            <p className="text-sm">填写话题并点击生成，结果展示在这里</p>
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center rounded-lg"
            style={{ height: 320, background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            <p className="text-sm">AI 生成中，请稍候…</p>
          </div>
        )}

        {result && (
          <div className="space-y-3">
            <div className="rounded-lg p-4 space-y-1"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>标题</p>
              <p className="text-base font-bold leading-snug">{result.title}</p>
            </div>

            <div className="rounded-lg p-4 space-y-2"
              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>正文</p>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{result.body}</p>
            </div>

            {result.tags.length > 0 && (
              <div className="rounded-lg p-4 space-y-2"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>标签</p>
                <div className="flex flex-wrap gap-1.5">
                  {result.tags.map((t, i) => (
                    <span key={i} className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: "color-mix(in srgb, var(--accent) 12%, var(--background))", color: "var(--accent)", border: "1px solid color-mix(in srgb, var(--accent) 25%, transparent)" }}>
                      {t.startsWith("#") ? t : `#${t}`}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <button onClick={() => setShowPrompt(v => !v)}
              className="text-xs px-3 py-1.5 rounded w-full"
              style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
              {showPrompt ? "▲ 收起完整 Prompt" : "▼ 查看填充后的完整 Prompt"}
            </button>
            {showPrompt && (
              <pre className="text-xs p-4 rounded whitespace-pre-wrap leading-relaxed overflow-auto"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", maxHeight: 360 }}>
                {result.filled_prompt}
              </pre>
            )}

            <button onClick={run} disabled={loading}
              className="w-full py-2 rounded text-sm disabled:opacity-50"
              style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
              ↺ 再生成一次
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 图片调试 tab ──────────────────────────────────────────────────────────────

function ImageDebugTab({
  accountId, strategy,
}: {
  accountId: number; strategy: StrategyData;
}) {
  const [title, setTitle]               = useState("");
  const [unusedTopics, setUnusedTopics] = useState<string[]>([]);
  const [topicIdx, setTopicIdx]         = useState(0);
  const [prompt, setPrompt]             = useState("");
  const [imagePath, setImagePath]       = useState("");
  const [templates, setTemplates]       = useState<ImageTemplate[]>([]);
  const [selectedTplId, setSelectedTplId] = useState<number | null>(null);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState("");
  const [result, setResult]             = useState<{ image_url: string; effective_prompt: string } | null>(null);
  const [showPrompt, setShowPrompt]     = useState(false);
  const [uploading, setUploading]       = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // 保存为模板的状态
  const [savingTpl, setSavingTpl]       = useState(false);
  const [tplName, setTplName]           = useState("");
  const [showTplInput, setShowTplInput] = useState(false);
  const [tplMsg, setTplMsg]             = useState("");
  const [previewOpen, setPreviewOpen]   = useState(true);

  // 实时渲染图片提示词
  const filledPrompt = useMemo(() => {
    if (!prompt) return "";
    return prompt
      .replaceAll("{niche}", strategy.niche || "（未设置）")
      .replaceAll("{title}", title || "（未填写）");
  }, [prompt, title, strategy.niche]);

  // 账号切换时加载图片模板列表 + 图片策略默认提示词 + 未用选题
  useEffect(() => {
    setResult(null);
    setTplMsg("");
    setSelectedTplId(null);

    // 先加载保存的图片模板（预设），有则用第一个；无则用策略默认提示词
    api.strategy.listImageTemplates(accountId).then(tpls => {
      setTemplates(tpls);
      const first = tpls[0];
      if (first) {
        setSelectedTplId(first.id);
        setPrompt(first.items[0]?.prompt ?? "");
        setImagePath(first.items[0]?.image_path ?? "");
      } else {
        api.strategy.getImage(accountId).then(s => {
          setPrompt(s.prompt_template ?? "");
        }).catch(() => {});
        setImagePath("");
      }
    }).catch(() => {
      api.strategy.getImage(accountId).then(s => {
        setPrompt(s.prompt_template ?? "");
      }).catch(() => {});
    });

    api.topics.list(accountId, undefined, 0).then(topics => {
      const list = topics.map(t => t.content);
      setUnusedTopics(list);
      setTopicIdx(0);
      setTitle(list[0] ?? "");
    }).catch(() => {});
  }, [accountId]);

  function selectTemplate(tpl: ImageTemplate) {
    setSelectedTplId(tpl.id);
    setPrompt(tpl.items[0]?.prompt ?? "");
    setImagePath(tpl.items[0]?.image_path ?? "");
  }

  function swapTitle() {
    if (unusedTopics.length === 0) return;
    const next = (topicIdx + 1) % unusedTopics.length;
    setTopicIdx(next);
    setTitle(unusedTopics[next]);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.strategy.uploadReferenceImage(accountId, file);
      setImagePath(res.path);
    } catch (err) {
      setError("上传失败：" + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function run() {
    if (!prompt.trim()) { setError("请填写图片提示词"); return; }
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const res = await api.debug.image({
        account_id: accountId,
        title: title.trim(),
        prompt: prompt.trim(),
        image_path: imagePath || undefined,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  }

  async function saveAsTemplate() {
    if (!tplName.trim()) return;
    setSavingTpl(true);
    try {
      const created = await api.strategy.createImageTemplate(accountId, {
        name: tplName.trim(),
        items: [{ image_path: imagePath || "", prompt: prompt.trim() }],
      });
      // 追加到列表并自动选中新建的模板
      setTemplates(prev => [...prev, created]);
      setSelectedTplId(created.id);
      setTplMsg(`已添加模板「${created.name}」`);
      setShowTplInput(false);
      setTplName("");
    } catch (e) {
      setTplMsg("保存失败：" + (e instanceof Error ? e.message : "未知错误"));
    } finally {
      setSavingTpl(false);
      setTimeout(() => setTplMsg(""), 3000);
    }
  }

  return (
    <div className="grid grid-cols-2 gap-6 items-start">

      {/* 左：配置 */}
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium" style={{ color: "var(--muted)" }}>
              文案标题（对应 <code style={{ color: "var(--accent)" }}>{"{title}"}</code>）
              {unusedTopics.length > 0 && (
                <span className="ml-1.5 font-normal" style={{ color: "var(--muted)" }}>
                  （选题库 {unusedTopics.length} 条）
                </span>
              )}
            </label>
            {unusedTopics.length > 1 && (
              <button onClick={swapTitle}
                className="text-xs px-2 py-0.5 rounded"
                style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                换一个
              </button>
            )}
          </div>
          <input value={title} onChange={e => setTitle(e.target.value)}
            placeholder="选题库为空时可手动输入"
            className="w-full text-sm px-3 py-2 rounded" style={inputStyle} />
        </div>

        <VarTable strategy={strategy} mode="image" imageTitle={title} />

        {/* 图片预设选择 */}
        {templates.length > 0 && (
          <div>
            <label className="block text-xs mb-1.5 font-medium" style={{ color: "var(--muted)" }}>图片预设</label>
            <div className="flex flex-wrap gap-2">
              {templates.map(tpl => (
                <button key={tpl.id} onClick={() => selectTemplate(tpl)}
                  className="text-xs px-3 py-1.5 rounded transition-colors"
                  style={{
                    background: selectedTplId === tpl.id ? "color-mix(in srgb, var(--accent) 12%, var(--background))" : "var(--surface)",
                    border: `1px solid ${selectedTplId === tpl.id ? "var(--accent)" : "var(--border)"}`,
                    color: selectedTplId === tpl.id ? "var(--accent)" : "var(--foreground)",
                  }}>
                  {tpl.name}
                </button>
              ))}
              <button onClick={() => { setSelectedTplId(null); api.strategy.getImage(accountId).then(s => { setPrompt(s.prompt_template ?? ""); setImagePath(""); }).catch(() => {}); }}
                className="text-xs px-3 py-1.5 rounded"
                style={{
                  background: selectedTplId === null ? "color-mix(in srgb, var(--accent) 12%, var(--background))" : "transparent",
                  border: `1px solid ${selectedTplId === null ? "var(--accent)" : "var(--border)"}`,
                  color: selectedTplId === null ? "var(--accent)" : "var(--muted)",
                }}>
                默认提示词
              </button>
            </div>
          </div>
        )}

        <div>
          <label className="block text-xs mb-1.5 font-medium" style={{ color: "var(--muted)" }}>图片提示词 *</label>
          <textarea value={prompt} onChange={e => setPrompt(e.target.value)}
            rows={6} className="w-full text-sm px-3 py-2.5 rounded resize-y font-mono"
            style={inputStyle} />
        </div>

        {/* 实际运行 Prompt 预览 */}
        <div className="rounded overflow-hidden" style={{ border: "1px solid var(--border)" }}>
          <button onClick={() => setPreviewOpen(v => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium"
            style={{ background: "var(--background)", color: "var(--muted)" }}>
            <span>实际运行的 Prompt</span>
            <span>{previewOpen ? "▲" : "▼"}</span>
          </button>
          {previewOpen && (
            <pre className="text-xs px-3 py-3 whitespace-pre-wrap leading-relaxed overflow-auto font-mono"
              style={{ background: "var(--background)", color: "var(--foreground)", maxHeight: 200, borderTop: "1px solid var(--border)" }}>
              {filledPrompt || <span style={{ color: "var(--muted)", fontStyle: "italic" }}>填写提示词后自动渲染…</span>}
            </pre>
          )}
        </div>

        <div>
          <label className="block text-xs mb-1.5 font-medium" style={{ color: "var(--muted)" }}>参考图（可选）</label>
          {imagePath ? (
            <div className="flex items-center gap-3">
              <img src={`/api/content/${accountId}/image?path=${encodeURIComponent(imagePath)}`}
                alt="参考图" className="w-16 h-16 object-cover rounded"
                style={{ border: "1px solid var(--border)" }} />
              <div className="space-y-1">
                <p className="text-xs truncate max-w-32" style={{ color: "var(--muted)" }}>
                  {imagePath.split("/").pop()}
                </p>
                <button onClick={() => setImagePath("")}
                  className="text-xs px-2 py-0.5 rounded"
                  style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                  移除
                </button>
              </div>
            </div>
          ) : (
            <label className="flex items-center gap-2 cursor-pointer text-xs px-3 py-2 rounded w-fit"
              style={{ border: "1px dashed var(--border)", color: "var(--muted)" }}>
              <input ref={fileRef} type="file" accept="image/*" onChange={handleUpload} className="hidden" />
              {uploading ? "上传中…" : "+ 上传参考图"}
            </label>
          )}
        </div>

        {error && (
          <p className="text-xs px-3 py-2 rounded"
            style={{ background: "color-mix(in srgb,#ef4444 10%,transparent)", color: "#ef4444", border: "1px solid color-mix(in srgb,#ef4444 25%,transparent)" }}>
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button onClick={run} disabled={loading}
            className="flex-1 py-2.5 rounded text-sm font-medium disabled:opacity-50"
            style={{ background: "var(--accent)", color: "#fff" }}>
            {loading ? "生成中…" : "▶ 生成预览"}
          </button>
          <button onClick={() => setShowTplInput(v => !v)} disabled={!prompt.trim()}
            className="py-2.5 px-4 rounded text-sm disabled:opacity-40"
            style={{ border: "1px solid var(--border)", color: "var(--foreground)", whiteSpace: "nowrap" }}>
            添加到图片预设
          </button>
        </div>

        {showTplInput && (
          <div className="flex gap-2">
            <input value={tplName} onChange={e => setTplName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && saveAsTemplate()}
              placeholder="模板名称，例如：写实风格A"
              className="flex-1 text-sm px-3 py-2 rounded" style={inputStyle} />
            <button onClick={saveAsTemplate} disabled={savingTpl || !tplName.trim()}
              className="text-sm px-4 py-2 rounded disabled:opacity-50"
              style={{ background: "var(--accent)", color: "#fff" }}>
              {savingTpl ? "…" : "保存"}
            </button>
          </div>
        )}
        {tplMsg && (
          <p className="text-xs" style={{ color: "var(--accent)" }}>{tplMsg}</p>
        )}
      </div>

      {/* 右：结果 */}
      <div className="space-y-4">
        {!result && !loading && (
          <div className="flex items-center justify-center rounded-lg"
            style={{ height: 400, background: "var(--surface)", border: "1px dashed var(--border)", color: "var(--muted)" }}>
            <p className="text-sm">填写提示词并点击生成，图片展示在这里</p>
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-lg"
            style={{ height: 400, background: "var(--surface)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            <div className="w-8 h-8 rounded-full border-2 animate-spin"
              style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
            <p className="text-sm">AI 生图中，通常需要 20–60 秒…</p>
          </div>
        )}

        {result && (
          <div className="space-y-3">
            <div className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)" }}>
              <img src={result.image_url} alt="生成结果"
                className="w-full object-contain"
                style={{ maxHeight: 520, background: "var(--background)" }} />
            </div>

            <button onClick={() => setShowPrompt(v => !v)}
              className="text-xs px-3 py-1.5 rounded w-full"
              style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
              {showPrompt ? "▲ 收起实际发送的 Prompt" : "▼ 查看实际发送的 Prompt"}
            </button>
            {showPrompt && (
              <pre className="text-xs p-4 rounded whitespace-pre-wrap leading-relaxed"
                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                {result.effective_prompt}
              </pre>
            )}

            <button onClick={run} disabled={loading}
              className="w-full py-2 rounded text-sm disabled:opacity-50"
              style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
              ↺ 再生成一次
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── 主页 ──────────────────────────────────────────────────────────────────────

export default function DebugPage() {
  const [tab, setTab]           = useState<Tab>("copy");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState(1);
  const [strategy, setStrategy] = useState<StrategyData>(emptyStrategy());

  // 加载账号列表
  useEffect(() => {
    api.accounts.list().then(list => {
      setAccounts(list);
      if (list.length > 0 && !list.find(a => a.id === accountId)) {
        setAccountId(list[0].id);
      }
    }).catch(() => {});
  }, []);

  // 切换账号时加载策略数据（用于变量渲染）
  const loadStrategy = useCallback((id: number) => {
    api.strategy.get(id).then(s => {
      try {
        const data = typeof s.data === "string" ? JSON.parse(s.data) : s.data;
        setStrategy({
          niche:                data.niche || "",
          target_audience:      data.target_audience || "",
          tone:                 data.tone || "",
          competitive_advantage: data.competitive_advantage || "",
          opening_style:        data.opening_style || "",
          format_style:         data.format_style || "",
          emoji_usage:          data.emoji_usage || "",
          content_length:       data.content_length || "",
          pain_points:          Array.isArray(data.pain_points) ? data.pain_points : [],
          forbidden_words:      Array.isArray(data.forbidden_words) ? data.forbidden_words : [],
          content_pillars:      Array.isArray(data.content_pillars) ? data.content_pillars : [],
        });
      } catch {
        setStrategy(emptyStrategy());
      }
    }).catch(() => setStrategy(emptyStrategy()));
  }, []);

  useEffect(() => { loadStrategy(accountId); }, [accountId, loadStrategy]);

  const tabs: { key: Tab; label: string }[] = [
    { key: "copy",  label: "文案指令" },
    { key: "image", label: "图片指令" },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5">
      {/* 页头 */}
      <div>
        <h1 className="text-lg font-semibold">指令调试</h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--muted)" }}>
          沙盒环境 — 生成结果不入库、不推飞书，随意测试提示词效果
        </p>
      </div>

      {/* 账号选择 */}
      {accounts.length > 0 && (
        <AccountSelector accounts={accounts} value={accountId} onChange={id => setAccountId(id)} />
      )}

      {/* Tab 切换 */}
      <div className="flex gap-1 p-1 rounded-lg w-fit"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className="text-sm px-5 py-1.5 rounded transition-colors"
            style={{
              background: tab === t.key ? "var(--accent)" : "transparent",
              color: tab === t.key ? "#fff" : "var(--muted)",
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* 沙盒提示 */}
      <div className="rounded-lg px-4 py-2.5 text-xs flex items-center gap-2"
        style={{ background: "color-mix(in srgb, #f59e0b 8%, transparent)", border: "1px solid color-mix(in srgb, #f59e0b 25%, transparent)", color: "#92400e" }}>
        ⚡ 调试生成不消耗选题库，不影响审核队列。
      </div>

      {/* Tab 内容 */}
      {tab === "copy"  && <CopyDebugTab  accountId={accountId} strategy={strategy} />}
      {tab === "image" && <ImageDebugTab accountId={accountId} strategy={strategy} />}
    </div>
  );
}
