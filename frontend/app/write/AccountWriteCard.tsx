"use client";

import { useEffect, useRef, useState } from "react";
import { api, Account, Topic, ContentType, ImageStrategy, ImageTemplate, ImageTemplateItem } from "@/lib/api";

// ── 常量 ─────────────────────────────────────────────────────────────────────

const GEN_STEPS = [
  { key: "topic", label: "准备选题" },
  { key: "ai",    label: "AI 生成文案" },
  { key: "image", label: "生成配图" },
  { key: "queue", label: "推送飞书" },
];

type ImageMode = "both" | "cards" | "ai";
interface Pillar { name: string; description: string }
type TabKey = "positioning" | "topics" | "copy" | "image";

const TONE_OPTIONS   = ["口语化", "专业感", "干货型", "生活感", "娱乐性", "故事型"];
const OPENING_STYLES = ["痛点戳入", "数字吸引", "故事开场", "提问引发", "悬念制造"];
const FORMAT_STYLES  = ["分点列举", "叙述型", "干货罗列", "对话体", "清单式"];
const EMOJI_OPTIONS  = ["不用", "适量", "丰富"];
const LENGTH_OPTIONS = ["200-400字", "300-500字", "500-800字"];

const IMG_MODES = [
  { value: "both",  label: "AI 封面 + 卡片", desc: "AI 生成封面，再渲染图文卡片" },
  { value: "cards", label: "图文卡片",        desc: "渲染器生成多张主题图文卡片" },
  { value: "ai",    label: "AI 生图",         desc: "仅用 AI 生成封面图" },
];

const CARD_THEMES = [
  { value: "default",           label: "优雅白",   gradient: "linear-gradient(180deg,#f5f5f5 0%,#e0e0e0 100%)", textColor: "#333" },
  { value: "sketch",            label: "紫韵",     gradient: "linear-gradient(180deg,#3450E4 0%,#D266DA 100%)",  textColor: "#fff" },
  { value: "playful-geometric", label: "小红书红", gradient: "linear-gradient(180deg,#FF2442 0%,#FF6B81 100%)",  textColor: "#fff" },
  { value: "botanical",         label: "清新薄荷", gradient: "linear-gradient(180deg,#43e97b 0%,#38f9d7 100%)",  textColor: "#fff" },
  { value: "retro",             label: "日落橙",   gradient: "linear-gradient(180deg,#fa709a 0%,#fee140 100%)",  textColor: "#fff" },
  { value: "professional",      label: "深海蓝",   gradient: "linear-gradient(180deg,#4facfe 0%,#00f2fe 100%)",  textColor: "#fff" },
  { value: "neo-brutalism",     label: "暗黑",     gradient: "linear-gradient(180deg,#1a1a2e 0%,#16213e 100%)",  textColor: "#e94560" },
];

const DEFAULT_IMG_TEMPLATE_PROMPT = "小红书封面图，{niche}领域，主题：{title}，风格简约清新，高质量摄影感，柔和光线，构图精美";

const DEFAULT_PROMPT = `你是一个专注于{niche}领域的小红书博主。

目标受众：{target_audience}
语气风格：{tone}
开场方式：{opening_style}
行文格式：{format_style}
Emoji 用量：{emoji_usage}
正文字数：{content_length}
内容方向：{content_pillars}
差异化优势：{competitive_advantage}
目标痛点：{pain_points}
禁止词汇：{forbidden_words}

请以【{topic}】为主题，创作一篇小红书笔记。

创作要求：
1. 标题：不超过20字，有吸引力，可加数字或疑问句形式
2. 正文：严格遵守上方字数、语气、格式等要求
3. 标签：9个相关话题标签，纯文字，不加 # 号

禁止：正文中不要出现"关注/点赞/收藏"等引导词。

严格按以下 JSON 格式输出，不要有任何额外文字：
\`\`\`json
{
  "title": "标题",
  "content": "正文",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5", "标签6", "标签7", "标签8", "标签9"]
}
\`\`\``;

const inputStyle = { background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)" };

// ── 子组件 ────────────────────────────────────────────────────────────────────

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-xs px-3 py-1.5 rounded-full transition-colors"
      style={{
        background: active ? "var(--accent)" : "var(--background)",
        color: active ? "#fff" : "var(--muted)",
        border: "1px solid var(--border)",
      }}>
      {label}
    </button>
  );
}

function MiniTheme({ theme, selected, onClick }: { theme: typeof CARD_THEMES[0]; selected: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="rounded overflow-hidden transition-all"
      style={{ border: `2px solid ${selected ? "var(--accent)" : "var(--border)"}` }}>
      <div className="w-full aspect-[3/4] relative" style={{ background: theme.gradient }}>
        <div className="absolute inset-0 flex flex-col justify-between p-1.5">
          <div>
            <div className="h-1.5 rounded-full mb-1" style={{ background: theme.textColor, opacity: 0.9, width: "80%" }} />
            <div className="h-1 rounded-full" style={{ background: theme.textColor, opacity: 0.5, width: "55%" }} />
          </div>
          <div className="space-y-0.5">
            {[100, 85, 70].map((w, i) => (
              <div key={i} className="h-0.5 rounded-full" style={{ background: theme.textColor, opacity: 0.3, width: `${w}%` }} />
            ))}
          </div>
        </div>
        {selected && (
          <div className="absolute top-1 right-1 w-4 h-4 rounded-full flex items-center justify-center font-bold"
            style={{ background: "var(--accent)", color: "#fff", fontSize: 9 }}>✓</div>
        )}
      </div>
      <p className="text-xs py-1 text-center truncate"
        style={{ color: selected ? "var(--accent)" : "var(--muted)", fontWeight: selected ? 600 : 400, background: "var(--background)" }}>
        {theme.label}
      </p>
    </button>
  );
}

function SaveBtn({ saving, saved, onClick, label = "保存" }: { saving: boolean; saved: boolean; onClick: () => void; label?: string }) {
  return (
    <button onClick={onClick} disabled={saving} className="px-6 py-2 rounded text-sm disabled:opacity-50"
      style={{ background: saved ? "#22c55e" : "var(--accent)", color: "#fff" }}>
      {saving ? "保存中…" : saved ? "✓ 已保存" : label}
    </button>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs mb-2" style={{ color: "var(--muted)" }}>{children}</label>;
}

function refImageUrl(accountId: number, path: string): string {
  return `/api/content/${accountId}/image?path=${encodeURIComponent(path)}`;
}

// ── 模板条目编辑器（单条，不再有多条目概念）────────────────────────────────────

function TemplateItemEditor({
  item, accountId, onChange,
}: {
  item: ImageTemplateItem; accountId: number;
  onChange: (item: ImageTemplateItem) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const result = await api.strategy.uploadReferenceImage(accountId, file);
      onChange({ ...item, image_path: result.path });
    } catch (err) {
      alert("上传失败：" + (err instanceof Error ? err.message : "未知错误"));
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="text-xs mb-1.5" style={{ color: "var(--muted)" }}>参考图片（可选）</p>
        {item.image_path ? (
          <div className="flex items-start gap-3">
            <img src={refImageUrl(accountId, item.image_path)} alt="参考图"
              className="w-20 h-20 object-cover rounded flex-shrink-0"
              style={{ border: "1px solid var(--border)" }} />
            <div className="flex flex-col gap-1.5 justify-center">
              <span className="text-xs" style={{ color: "var(--muted)" }}>
                {item.image_path.split("/").pop()}
              </span>
              <button onClick={() => onChange({ ...item, image_path: "" })}
                className="text-xs px-2 py-1 rounded w-fit"
                style={{ color: "var(--muted)", border: "1px solid var(--border)" }}>
                移除
              </button>
            </div>
          </div>
        ) : (
          <label className="flex flex-col items-center justify-center gap-1.5 rounded cursor-pointer"
            style={{ border: "2px dashed var(--border)", width: 80, height: 80, color: "var(--muted)" }}>
            <input ref={fileRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
            {uploading ? (
              <span className="text-xs">上传中…</span>
            ) : (
              <>
                <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path d="M4 16l4-4 4 4 4-6 4 6" /><rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                </svg>
                <span className="text-xs text-center leading-tight">点击上传<br/>参考图</span>
              </>
            )}
          </label>
        )}
      </div>

      <div>
        <p className="text-xs mb-1" style={{ color: "var(--muted)" }}>提示词</p>
        <textarea value={item.prompt} onChange={e => onChange({ ...item, prompt: e.target.value })}
          placeholder="描述图片风格或内容，例如：小红书封面图，{niche}领域，主题：{title}"
          rows={6} className="w-full text-sm p-2 rounded resize-y" style={inputStyle} />
      </div>
    </div>
  );
}

// ── 模板卡片 ──────────────────────────────────────────────────────────────────

function TemplateCard({
  tpl, accountId, onActivate, onEdit, onDelete,
}: {
  tpl: ImageTemplate; accountId: number;
  onActivate?: () => void; onEdit: () => void; onDelete: () => void;
}) {
  const thumbItems = tpl.items.filter(i => i.image_path).slice(0, 3);
  const firstPrompt = tpl.items.find(i => i.prompt)?.prompt ?? "";

  return (
    <div className="rounded p-3 space-y-2"
      style={{ background: "var(--surface)", border: `1px solid ${tpl.is_active && onActivate ? "var(--accent)" : "var(--border)"}` }}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium flex-1">{tpl.name}</span>
        {tpl.is_active && onActivate && (
          <span className="text-xs px-2 py-0.5 rounded font-medium"
            style={{ background: "color-mix(in srgb, var(--accent) 15%, transparent)", color: "var(--accent)" }}>
            当前使用
          </span>
        )}
      </div>

      {/* 缩略图 */}
      {thumbItems.length > 0 && (
        <div className="flex gap-1.5">
          {thumbItems.map((item, i) => (
            <img key={i} src={refImageUrl(accountId, item.image_path)}
              alt="参考图" className="w-12 h-12 object-cover rounded flex-shrink-0"
              style={{ border: "1px solid var(--border)" }} />
          ))}
          {tpl.items.filter(i => i.image_path).length > 3 && (
            <div className="w-12 h-12 rounded flex items-center justify-center text-xs flex-shrink-0"
              style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--muted)" }}>
              +{tpl.items.filter(i => i.image_path).length - 3}
            </div>
          )}
        </div>
      )}

      {/* 提示词摘要 */}
      {firstPrompt && (
        <p className="text-xs leading-relaxed line-clamp-2" style={{ color: "var(--muted)" }}>
          {firstPrompt}
        </p>
      )}

      {!thumbItems.length && !firstPrompt && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>空模板</p>
      )}

      <div className="flex gap-2 pt-1">
        {onActivate && !tpl.is_active && (
          <button onClick={onActivate} className="text-xs px-3 py-1 rounded"
            style={{ background: "var(--accent)", color: "#fff" }}>
            设为当前
          </button>
        )}
        <button onClick={onEdit} className="text-xs px-3 py-1 rounded"
          style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
          编辑
        </button>
        <button onClick={onDelete} className="text-xs px-3 py-1 rounded ml-auto"
          style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
          删除
        </button>
      </div>
    </div>
  );
}

// ── 模板编辑 Modal ────────────────────────────────────────────────────────────

function TemplateEditor({
  initial, accountId, onSave, onCancel,
}: {
  initial: Partial<ImageTemplate> | null;
  accountId: number;
  onSave: (name: string, items: ImageTemplateItem[]) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [item, setItem] = useState<ImageTemplateItem>(
    initial?.items?.[0] ?? { image_path: "", prompt: DEFAULT_IMG_TEMPLATE_PROMPT }
  );
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!name.trim()) { alert("请输入模板名称"); return; }
    setSaving(true);
    try { await onSave(name.trim(), [item]); } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.5)" }}>
      <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl p-6 space-y-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <h3 className="font-semibold">{initial?.id ? "编辑模板" : "新建模板"}</h3>

        <div>
          <label className="block text-xs mb-1" style={{ color: "var(--muted)" }}>模板名称</label>
          <input value={name} onChange={e => setName(e.target.value)}
            placeholder="例如：风景参考图、品牌风格A"
            className="w-full text-sm px-3 py-2 rounded" style={inputStyle} />
        </div>

        <div className="rounded text-xs overflow-hidden"
          style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
          <div className="px-3 py-1 font-semibold" style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>
            提示词可用变量
          </div>
          <table className="w-full">
            <tbody>
              {([
                { key: "{niche}",  desc: "账号方向", note: "在账号定位里配置" },
                { key: "{title}",  desc: "文案标题", note: "运行时由 AI 生成" },
              ] as { key: string; desc: string; note: string }[]).map(v => (
                <tr key={v.key} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td className="px-3 py-1.5 w-24 font-mono"><code style={{ color: "var(--accent)" }}>{v.key}</code></td>
                  <td className="px-3 py-1.5 w-20" style={{ color: "var(--muted)" }}>{v.desc}</td>
                  <td className="px-3 py-1.5" style={{ color: "var(--muted)", fontStyle: "italic" }}>{v.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <TemplateItemEditor item={item} accountId={accountId} onChange={setItem} />

        <div className="flex gap-3 pt-2">
          <button onClick={handleSave} disabled={saving}
            className="flex-1 py-2 rounded text-sm font-medium disabled:opacity-50"
            style={{ background: "var(--accent)", color: "#fff" }}>
            {saving ? "保存中…" : "保存"}
          </button>
          <button onClick={onCancel} className="flex-1 py-2 rounded text-sm"
            style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
            取消
          </button>
        </div>
      </div>
    </div>
  );
}

// ── 主卡片组件 ────────────────────────────────────────────────────────────────

export default function AccountWriteCard({ account }: { account: Account }) {
  const accId    = account.id;
  const accLabel = account.display_name || account.nickname || `账号 ${accId}`;

  const [expanded, setExpanded] = useState(false);
  const [loaded, setLoaded]     = useState(false);

  // ── 账号定位 ──
  const [niche, setNiche]               = useState("");
  const [audience, setAudience]         = useState("");
  const [advantage, setAdvantage]       = useState("");
  const [monetization, setMonetization] = useState("");
  const [posSaving, setPosSaving]       = useState(false);
  const [posSaved, setPosSaved]         = useState(false);

  // ── 选题库 ──
  const [topicCount, setTopicCount]       = useState(0);
  const [topicList, setTopicList]         = useState<Topic[]>([]);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topicFilter, setTopicFilter]     = useState<"all" | "unused" | "used">("unused");
  const [singleContent, setSingleContent] = useState("");
  const [singleAdding, setSingleAdding]   = useState(false);
  const [quickTopics, setQuickTopics]     = useState("");
  const [topicsAdding, setTopicsAdding]   = useState(false);
  const [topicsAdded, setTopicsAdded]     = useState(false);
  const [inspiration, setInspiration]     = useState("");
  const [aiGenerating, setAiGenerating]   = useState(false);
  const [aiOptions, setAiOptions]         = useState<string[]>([]);
  const [aiSelected, setAiSelected]       = useState<Set<number>>(new Set());
  const [addingAi, setAddingAi]           = useState(false);
  const [aiMsg, setAiMsg]                 = useState("");

  // ── 文案预设 ──
  const [activeTab, setActiveTab]           = useState<TabKey>("positioning");
  const [tone, setTone]                     = useState("口语化");
  const [openingStyle, setOpeningStyle]     = useState("痛点戳入");
  const [formatStyle, setFormatStyle]       = useState("分点列举");
  const [emojiUsage, setEmojiUsage]         = useState("适量");
  const [contentLength, setContentLength]   = useState("300-500字");
  const [painPoints, setPainPoints]         = useState<string[]>([]);
  const [newPainPoint, setNewPainPoint]     = useState("");
  const [forbidden, setForbidden]           = useState<string[]>([]);
  const [newForbidden, setNewForbidden]     = useState("");
  const [pillars, setPillars]               = useState<Pillar[]>([]);
  const [contentTypes, setContentTypes]     = useState<ContentType[]>([]);
  const [promptTemplate, setPromptTemplate] = useState(DEFAULT_PROMPT);
  const [promptTypeId, setPromptTypeId]     = useState<number | null>(null);
  const [copySaving, setCopySaving]         = useState(false);
  const [copySaved, setCopySaved]           = useState(false);
  const [showPromptPreview, setShowPromptPreview] = useState(false);

  // ── 图片预设 ──
  const [imgMode, setImgMode]           = useState("cards");
  const [cardTheme, setCardTheme]       = useState("default");
  const [imgPrompt, setImgPrompt]       = useState("");
  const [imgRefImages, setImgRefImages] = useState<string[]>([]);
  const [templateMode, setTemplateMode] = useState<"specific" | "random">("specific");
  const [imgSaving, setImgSaving]       = useState(false);
  const [imgSaved, setImgSaved]         = useState(false);
  const [templates, setTemplates]       = useState<ImageTemplate[]>([]);
  const [editingTpl, setEditingTpl]     = useState<Partial<ImageTemplate> | null | false>(false);

  // ── 生成选项 ──
  const [topicMode, setTopicMode]         = useState<"auto" | "manual" | "pick">("auto");
  const [manualTopic, setManualTopic]     = useState("");
  const [pickedTopic, setPickedTopic]     = useState<Topic | null>(null);
  const [selectedPillar, setSelectedPillar] = useState("");
  const [imageMode, setImageMode]         = useState<ImageMode>("both");

  // ── 生成状态 ──
  const [genStep, setGenStep]       = useState(-1);
  const [genError, setGenError]     = useState("");
  const [genSuccess, setGenSuccess] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // mount 时加载收起状态预览所需的最小数据（niche + 选题数量）
  useEffect(() => {
    Promise.all([
      api.strategy.get(accId).catch(() => null),
      api.topics.stats(accId).catch(() => null),
    ]).then(([strat, stats]) => {
      if (strat && !loaded) {
        let d: Record<string, unknown> = {};
        try { d = JSON.parse(strat.data ?? "{}"); } catch { /**/ }
        setNiche((d.niche as string) || "");
      }
      if (stats && !loaded) setTopicCount(stats.unused ?? 0);
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accId]);

  // 首次展开时加载完整数据
  useEffect(() => {
    if (!expanded || loaded) return;
    Promise.all([
      api.strategy.get(accId).catch(() => null),
      api.topics.stats(accId).catch(() => null),
      api.strategy.getImage(accId).catch(() => null),
      api.topics.listTypes(accId).catch(() => []),
      api.strategy.listImageTemplates(accId).catch(() => []),
    ]).then(([strat, stats, img, types, tpls]) => {
      if (strat) {
        let d: Record<string, unknown> = {};
        try { d = JSON.parse(strat.data ?? "{}"); } catch { /**/ }
        setNiche((d.niche as string) || "");
        setAudience((d.target_audience as string) || "");
        setAdvantage((d.competitive_advantage as string) || "");
        setMonetization((d.monetization as string) || "");
        setTone((d.tone as string) || "口语化");
        setOpeningStyle((d.opening_style as string) || "痛点戳入");
        setFormatStyle((d.format_style as string) || "分点列举");
        setEmojiUsage((d.emoji_usage as string) || "适量");
        setContentLength((d.content_length as string) || "300-500字");
        setPainPoints((d.pain_points as string[]) || []);
        setForbidden((d.forbidden_words as string[]) || []);
        const p = d.content_pillars as Pillar[] | undefined;
        if (p?.length) setPillars(p.filter(x => x.name?.trim()));
      }
      if (stats) setTopicCount(stats.unused ?? 0);
      if (img) {
        setImgMode(img.mode || "cards");
        setCardTheme(img.card_theme || "default");
        setImgPrompt(img.prompt_template || "");
        setImgRefImages(img.reference_images || []);
        setTemplateMode((img.template_mode as "specific" | "random") || "specific");
      }
      const activeTypes = (types as ContentType[]).filter(t => t.is_active);
      setContentTypes(activeTypes);
      const firstType = activeTypes[0];
      if (firstType) { setPromptTemplate(firstType.prompt_template || DEFAULT_PROMPT); setPromptTypeId(firstType.id); }
      setTemplates((tpls as ImageTemplate[]) || []);
      setLoaded(true);
    });
  }, [expanded, loaded, accId]);

  // 选题库标签页激活时加载列表
  useEffect(() => {
    if (!expanded || activeTab !== "topics") return;
    setTopicsLoading(true);
    const isUsed = topicFilter === "unused" ? 0 : topicFilter === "used" ? 1 : undefined;
    api.topics.list(accId, undefined, isUsed)
      .then(setTopicList).catch(() => {}).finally(() => setTopicsLoading(false));
  }, [expanded, activeTab, topicFilter, accId]);

  // 挑选模式加载未用列表
  useEffect(() => {
    if (!expanded || topicMode !== "pick") return;
    setTopicsLoading(true);
    api.topics.list(accId, undefined, 0)
      .then(setTopicList).catch(() => {}).finally(() => setTopicsLoading(false));
  }, [expanded, topicMode, accId]);

  // ── 保存 ─────────────────────────────────────────────────────────────────────

  async function savePositioning() {
    setPosSaving(true); setPosSaved(false);
    try {
      await api.strategy.edit(accId, {
        niche, target_audience: audience, competitive_advantage: advantage, monetization,
        pain_points: painPoints,
        content_pillars: pillars.filter(p => p.name.trim()),
      });
      setPosSaved(true); setTimeout(() => setPosSaved(false), 2500);
    } catch { /**/ } finally { setPosSaving(false); }
  }

  async function saveCopyStrategy() {
    setCopySaving(true); setCopySaved(false);
    try {
      await api.strategy.edit(accId, {
        tone, opening_style: openingStyle, format_style: formatStyle,
        emoji_usage: emojiUsage, content_length: contentLength,
        pain_points: painPoints, forbidden_words: forbidden,
        content_pillars: pillars.filter(p => p.name.trim()),
      });
      if (promptTypeId) {
        await api.topics.updateType(accId, promptTypeId, { prompt_template: promptTemplate });
      } else {
        const types = await api.topics.initTypes(accId);
        if (types.length > 0) {
          await api.topics.updateType(accId, types[0].id, { prompt_template: promptTemplate });
          setPromptTypeId(types[0].id);
        }
      }
      setCopySaved(true); setTimeout(() => setCopySaved(false), 2500);
    } catch { /**/ } finally { setCopySaving(false); }
  }

  async function saveImageStrategy() {
    setImgSaving(true); setImgSaved(false);
    try {
      const body: ImageStrategy = { mode: imgMode, card_theme: cardTheme, prompt_template: imgPrompt, reference_images: imgRefImages, ai_model: null, template_mode: templateMode };
      await api.strategy.updateImage(accId, body);
      setImgSaved(true); setTimeout(() => setImgSaved(false), 2500);
    } catch { /**/ } finally { setImgSaving(false); }
  }

  // 模板管理
  async function activateTemplate(tplId: number) {
    await api.strategy.activateImageTemplate(accId, tplId);
    setTemplates(prev => prev.map(t => ({ ...t, is_active: t.id === tplId })));
  }
  async function deactivateTemplate() {
    await api.strategy.deactivateImageTemplates(accId);
    setTemplates(prev => prev.map(t => ({ ...t, is_active: false })));
  }
  async function deleteTemplate(tplId: number) {
    if (!confirm("确认删除该模板？")) return;
    await api.strategy.deleteImageTemplate(accId, tplId);
    setTemplates(prev => prev.filter(t => t.id !== tplId));
  }
  async function saveTemplate(name: string, items: ImageTemplateItem[]) {
    if (editingTpl && (editingTpl as ImageTemplate).id) {
      const updated = await api.strategy.updateImageTemplate(accId, (editingTpl as ImageTemplate).id, { name, items });
      setTemplates(prev => prev.map(t => t.id === updated.id ? updated : t));
    } else {
      const created = await api.strategy.createImageTemplate(accId, { name, items });
      setTemplates(prev => [...prev, created]);
    }
    setEditingTpl(false);
  }

  async function refreshTopics() {
    const isUsed = topicFilter === "unused" ? 0 : topicFilter === "used" ? 1 : undefined;
    const [stats, list] = await Promise.all([api.topics.stats(accId), api.topics.list(accId, undefined, isUsed)]);
    setTopicCount(stats.unused ?? 0);
    setTopicList(list);
  }

  async function addSingleTopic() {
    if (!singleContent.trim()) return;
    setSingleAdding(true);
    try {
      await api.topics.create(accId, { content_type: "通用", content: singleContent.trim() });
      setSingleContent("");
      await refreshTopics();
    } catch { /**/ } finally { setSingleAdding(false); }
  }

  async function quickAddTopics() {
    if (!quickTopics.trim()) return;
    setTopicsAdding(true); setTopicsAdded(false);
    try {
      await api.topics.batchImport(accId, "通用", quickTopics);
      setQuickTopics("");
      await refreshTopics();
      setTopicsAdded(true); setTimeout(() => setTopicsAdded(false), 2500);
    } catch { /**/ } finally { setTopicsAdding(false); }
  }

  async function generateInspiration() {
    if (!inspiration.trim()) return;
    setAiGenerating(true); setAiOptions([]); setAiSelected(new Set()); setAiMsg("");
    try {
      const res = await fetch(`/api/topics/${accId}/inspire`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: inspiration }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setAiOptions(data.options ?? []);
      if (!data.options?.length) setAiMsg("AI 没有生成选题，请换个方式描述灵感");
    } catch (e: unknown) { setAiMsg((e as Error).message); }
    finally { setAiGenerating(false); }
  }

  async function addAiSelected() {
    if (aiSelected.size === 0) return;
    setAddingAi(true);
    try {
      for (const content of aiOptions.filter((_, i) => aiSelected.has(i))) {
        await api.topics.create(accId, { content_type: "通用", content });
      }
      setAiOptions([]); setAiSelected(new Set()); setInspiration("");
      await refreshTopics();
    } catch { /**/ } finally { setAddingAi(false); }
  }

  async function deleteTopic(id: number) {
    await api.topics.delete(accId, id);
    setTopicList(prev => prev.filter(t => t.id !== id));
    setTopicCount(c => Math.max(0, c - 1));
  }

  function buildPromptPreview() {
    // 已知值直接替换；运行时才产生的值（topic、content_type）保持原占位符
    // 与后端 generate.py 逻辑保持一致：选了具体方向则只注入该方向，否则注入全部
    let pillarVal: string;
    if (selectedPillar) {
      const matched = pillars.find(p => p.name === selectedPillar);
      pillarVal = matched?.description ? `${selectedPillar}（${matched.description}）` : selectedPillar;
    } else {
      pillarVal = pillars.filter(p => p.name.trim())
        .map(p => p.name + (p.description ? `（${p.description}）` : "")).join("、");
    }
    return promptTemplate
      .replace(/\{niche\}/g,                niche || "{niche}")
      .replace(/\{target_audience\}/g,      audience || "{target_audience}")
      .replace(/\{tone\}/g,                 tone || "{tone}")
      .replace(/\{competitive_advantage\}/g, advantage || "{competitive_advantage}")
      .replace(/\{opening_style\}/g,        openingStyle || "{opening_style}")
      .replace(/\{format_style\}/g,         formatStyle || "{format_style}")
      .replace(/\{emoji_usage\}/g,          emojiUsage || "{emoji_usage}")
      .replace(/\{content_length\}/g,       contentLength || "{content_length}")
      .replace(/\{pain_points\}/g,          painPoints.length ? painPoints.join(" / ") : "{pain_points}")
      .replace(/\{forbidden_words\}/g,      forbidden.length ? forbidden.join(" ") : "{forbidden_words}")
      .replace(/\{content_pillars\}/g,      pillarVal || "{content_pillars}");
    // {topic} 和 {content_type} 不替换，运行时由系统注入
  }

  // ── 生成 ─────────────────────────────────────────────────────────────────────

  function stopPoll() {
    if (pollTimer.current) { clearInterval(pollTimer.current); pollTimer.current = null; }
  }

  async function generate() {
    if (topicMode === "manual" && !manualTopic.trim()) { setGenError("请输入选题"); return; }
    if (topicMode === "pick" && !pickedTopic) { setGenError("请选择一个选题"); return; }
    stopPoll();
    setGenError(""); setGenSuccess(false); setGenStep(0);

    let jobId: string;
    try {
      const topic = topicMode === "manual" ? manualTopic.trim() : topicMode === "pick" ? pickedTopic!.content : undefined;
      const res = await api.content.generate(accId, { topic, image_mode: imageMode, pillar: selectedPillar || undefined });
      jobId = res.job_id;
    } catch (e: unknown) {
      setGenStep(-1); setGenError((e as Error).message);
      return;
    }

    pollTimer.current = setInterval(async () => {
      try {
        const job = await api.content.pollJob(jobId);
        setGenStep(job.step);
        if (job.status === "done") {
          stopPoll();
          setGenStep(4); setGenSuccess(true);
          setTimeout(() => {
            setGenStep(-1); setGenSuccess(false);
          }, 3000);
        } else if (job.status === "error") {
          stopPoll();
          setGenStep(-1); setGenError(job.error || "生成失败，请检查选题库和 AI 配置");
        }
      } catch { /**/ }
    }, 2000);
  }

  const generating = genStep >= 0 && genStep < 4;

  const radioStyle = (active: boolean) => ({
    border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
    background: active ? "color-mix(in srgb, var(--accent) 6%, var(--background))" : "var(--background)",
    color: active ? "var(--accent)" : "var(--foreground)",
  });

  const TABS: { key: TabKey; label: string; ok: boolean }[] = [
    { key: "positioning", label: "账号定位", ok: !!niche },
    { key: "topics",      label: "选题库",   ok: topicCount > 0 },
    { key: "copy",        label: "文案预设",  ok: true },
    { key: "image",       label: "图片预设",  ok: true },
  ];

  // ── 卡片头部（折叠状态）──────────────────────────────────────────────────────

  return (
    <div className="rounded-lg overflow-hidden" style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>

      {/* 头部 */}
      <div className="flex items-center gap-3 px-5 py-4">
        {/* 左侧：账号名 + 定位，点击展开/收起 */}
        <div className="flex-1 min-w-0 cursor-pointer select-none"
          onClick={() => setExpanded(v => !v)}>
          <p className="text-sm font-semibold truncate">{accLabel}</p>
          {niche && !expanded && (
            <p className="text-xs mt-0.5 truncate" style={{ color: "var(--muted)" }}>{niche}</p>
          )}
        </div>

        {/* 选题数量徽标 */}
        {topicCount > 0 && (
          <span className="text-xs px-2 py-1 rounded-full shrink-0"
            style={{ background: "color-mix(in srgb, #22c55e 12%, var(--background))", color: "#22c55e", border: "1px solid #22c55e44" }}>
            剩余 {topicCount} 条选题
          </span>
        )}
        {topicCount === 0 && (niche || loaded) && (
          <span className="text-xs px-2 py-1 rounded-full shrink-0"
            style={{ background: "var(--background)", color: "var(--muted)", border: "1px solid var(--border)" }}>
            无选题
          </span>
        )}

        {/* 收起状态下的快捷按钮 */}
        {!expanded && account.feishu_app_token && (
          <div className="flex items-center gap-1.5 shrink-0" onClick={e => e.stopPropagation()}>
            <a href={`https://feishu.cn/base/${account.feishu_app_token}${account.feishu_table_id ? `?table=${account.feishu_table_id}` : ""}`}
              target="_blank" rel="noopener noreferrer"
              title="打开飞书审核表格"
              className="text-xs px-2.5 py-1 rounded transition-colors"
              style={{ background: "var(--background)", color: "var(--muted)", border: "1px solid var(--border)" }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "var(--foreground)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "var(--muted)"; }}>
              飞书审核
            </a>
          </div>
        )}

        {/* 展开/收起箭头 */}
        <span className="text-xs shrink-0 cursor-pointer select-none" style={{ color: "var(--muted)" }}
          onClick={() => setExpanded(v => !v)}>
          {expanded ? "▲ 收起" : "▼ 展开"}
        </span>
      </div>

      {/* 展开内容 */}
      {expanded && (
        <div className="border-t px-5 pb-5 pt-4 space-y-5" style={{ borderColor: "var(--border)" }}>

          {!loaded ? (
            <p className="text-sm text-center py-8" style={{ color: "var(--muted)" }}>加载中…</p>
          ) : (
            <div className="grid grid-cols-5 gap-6 items-start">

              {/* 左栏：配置标签 */}
              <div className="col-span-3">
                <div className="flex gap-1 p-1 rounded-lg mb-4"
                  style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                  {TABS.map(tab => (
                    <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                      className="flex-1 px-3 py-2 rounded text-sm font-medium transition-all"
                      style={{
                        background: activeTab === tab.key ? "var(--surface)" : "transparent",
                        color: activeTab === tab.key ? "var(--foreground)" : "var(--muted)",
                        boxShadow: activeTab === tab.key ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
                      }}>
                      {tab.label}
                      {!tab.ok && <span className="ml-1.5 text-xs" style={{ color: "var(--accent)" }}>⚠</span>}
                    </button>
                  ))}
                </div>

                <div className="rounded-lg p-6" style={{ background: "var(--background)", border: "1px solid var(--border)", minHeight: 480 }}>

                  {/* 账号定位 */}
                  {activeTab === "positioning" && (
                    <div className="space-y-5">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label>账号方向 / 赛道</Label>
                          <input value={niche} onChange={e => setNiche(e.target.value)}
                            placeholder="例：职场成长、个人理财…"
                            className="w-full text-sm px-3 py-2.5 rounded" style={inputStyle} />
                        </div>
                        <div>
                          <Label>变现路径</Label>
                          <input value={monetization} onChange={e => setMonetization(e.target.value)}
                            placeholder="例：知识付费、接广告…"
                            className="w-full text-sm px-3 py-2.5 rounded" style={inputStyle} />
                        </div>
                      </div>
                      <div>
                        <Label>目标受众</Label>
                        <textarea value={audience} onChange={e => setAudience(e.target.value)}
                          placeholder="例：25-35岁职场女性，想提升竞争力，月收入1-3万"
                          rows={3} className="w-full text-sm px-3 py-2.5 rounded resize-none" style={inputStyle} />
                      </div>
                      <div>
                        <Label>差异化优势</Label>
                        <textarea value={advantage} onChange={e => setAdvantage(e.target.value)}
                          placeholder="例：有10年HR经验，专注分享被大多数人忽视的面试细节"
                          rows={3} className="w-full text-sm px-3 py-2.5 rounded resize-none" style={inputStyle} />
                      </div>
                      <div>
                        <Label>目标受众痛点</Label>
                        <div className="flex flex-wrap gap-1.5 mb-2 min-h-7">
                          {painPoints.map((p, i) => (
                            <span key={i} className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded"
                              style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                              {p}<button onClick={() => setPainPoints(prev => prev.filter((_, idx) => idx !== i))} style={{ color: "var(--muted)" }}>×</button>
                            </span>
                          ))}
                        </div>
                        <input value={newPainPoint} onChange={e => setNewPainPoint(e.target.value)}
                          onKeyDown={e => { if (e.key === "Enter" && newPainPoint.trim()) { setPainPoints(p => [...p, newPainPoint.trim()]); setNewPainPoint(""); } }}
                          placeholder="输入痛点，回车添加" className="w-full text-sm px-3 py-2.5 rounded" style={inputStyle} />
                      </div>
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <Label>内容方向（生成时可单独选择）</Label>
                          <button onClick={() => setPillars(prev => [...prev, { name: "", description: "" }])}
                            className="text-xs" style={{ color: "var(--accent)" }}>+ 添加方向</button>
                        </div>
                        {pillars.length === 0 ? (
                          <p className="text-xs py-2" style={{ color: "var(--muted)" }}>暂无内容方向</p>
                        ) : (
                          <div className="space-y-2">
                            {pillars.map((p, i) => (
                              <div key={i} className="flex gap-2 items-center">
                                <span className="text-xs w-5 text-center shrink-0" style={{ color: "var(--muted)" }}>{i + 1}</span>
                                <input value={p.name} onChange={e => setPillars(prev => prev.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
                                  placeholder="方向名称" className="text-sm px-3 py-2 rounded w-28 shrink-0" style={inputStyle} />
                                <input value={p.description} onChange={e => setPillars(prev => prev.map((x, idx) => idx === i ? { ...x, description: e.target.value } : x))}
                                  placeholder="简短描述" className="flex-1 text-sm px-3 py-2 rounded" style={inputStyle} />
                                <button onClick={() => setPillars(prev => prev.filter((_, idx) => idx !== i))} className="text-sm shrink-0" style={{ color: "var(--muted)" }}>×</button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                      <SaveBtn saving={posSaving} saved={posSaved} onClick={savePositioning} label="保存账号定位" />
                    </div>
                  )}

                  {/* 选题库 */}
                  {activeTab === "topics" && (
                    <div className="space-y-5">
                      <div className="flex items-center gap-4">
                        {[
                          { label: "未使用", value: topicCount, color: "#22c55e" },
                          { label: "已使用", value: (topicList.length > 0 && topicFilter === "used") ? topicList.length : "—", color: "var(--muted)" },
                        ].map(item => (
                          <div key={item.label} className="rounded-lg px-4 py-2 text-center"
                            style={{ background: "var(--surface)", border: "1px solid var(--border)", minWidth: 64 }}>
                            <p className="text-lg font-bold" style={{ color: item.color }}>{item.value}</p>
                            <p className="text-xs" style={{ color: "var(--muted)" }}>{item.label}</p>
                          </div>
                        ))}
                        <button onClick={async () => { await api.topics.resetAll(accId); await refreshTopics(); }}
                          className="text-xs px-4 py-2 rounded ml-auto"
                          style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                          重置全部已用
                        </button>
                      </div>

                      {/* AI 灵感生成 */}
                      <div className="rounded-lg p-4 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                        <div>
                          <p className="text-sm font-semibold mb-0.5">AI 生成选题</p>
                          <p className="text-xs" style={{ color: "var(--muted)" }}>随便说一个灵感或方向，AI 帮你出几个具体选题，勾选后加入库。</p>
                        </div>
                        <div className="flex gap-2">
                          <textarea value={inspiration} onChange={e => setInspiration(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); generateInspiration(); } }}
                            placeholder="例：想聊职场焦虑，或者关于副业那些坑…"
                            rows={2} className="flex-1 text-sm px-3 py-2.5 rounded resize-none" style={inputStyle} />
                          <button onClick={generateInspiration} disabled={aiGenerating || !inspiration.trim()}
                            className="text-xs px-4 py-2 rounded self-start disabled:opacity-50 shrink-0"
                            style={{ background: "var(--accent)", color: "#fff" }}>
                            {aiGenerating ? "生成中…" : "生成选题"}
                          </button>
                        </div>
                        {aiMsg && <p className="text-xs" style={{ color: "var(--muted)" }}>{aiMsg}</p>}
                        {aiOptions.length > 0 && (
                          <div className="space-y-2">
                            {aiOptions.map((opt, i) => (
                              <label key={i} className="flex items-start gap-3 px-3 py-2.5 rounded cursor-pointer"
                                style={{
                                  background: aiSelected.has(i) ? "color-mix(in srgb, var(--accent) 8%, var(--background))" : "var(--background)",
                                  border: `1px solid ${aiSelected.has(i) ? "var(--accent)" : "var(--border)"}`,
                                }}>
                                <input type="checkbox" checked={aiSelected.has(i)}
                                  onChange={() => setAiSelected(prev => { const n = new Set(prev); n.has(i) ? n.delete(i) : n.add(i); return n; })}
                                  className="mt-0.5 shrink-0" />
                                <span className="text-sm">{opt}</span>
                              </label>
                            ))}
                            <div className="flex gap-2 pt-1">
                              <button onClick={addAiSelected} disabled={addingAi || aiSelected.size === 0}
                                className="text-xs px-4 py-1.5 rounded disabled:opacity-50"
                                style={{ background: "var(--accent)", color: "#fff" }}>
                                {addingAi ? "添加中…" : `加入选题库（${aiSelected.size} 条）`}
                              </button>
                              <button onClick={() => { setAiOptions([]); setAiSelected(new Set()); }}
                                className="text-xs px-3 py-1.5 rounded"
                                style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                                清除
                              </button>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label>单条添加</Label>
                          <div className="flex gap-2">
                            <input value={singleContent} onChange={e => setSingleContent(e.target.value)}
                              onKeyDown={e => { if (e.key === "Enter") addSingleTopic(); }}
                              placeholder="输入一条，回车添加"
                              className="flex-1 text-sm px-3 py-2.5 rounded" style={inputStyle} />
                            <button onClick={addSingleTopic} disabled={singleAdding || !singleContent.trim()}
                              className="text-xs px-3 py-2 rounded disabled:opacity-50 shrink-0"
                              style={{ border: "1px solid var(--border)", color: "var(--foreground)" }}>
                              {singleAdding ? "…" : "添加"}
                            </button>
                          </div>
                        </div>
                        <div>
                          <Label>批量导入（每行一条）</Label>
                          <div className="flex gap-2 items-start">
                            <textarea value={quickTopics} onChange={e => setQuickTopics(e.target.value)}
                              placeholder={"被裁员后我做的第一件事\n副业第一个月收入"}
                              rows={2} className="flex-1 text-sm px-3 py-2.5 rounded resize-none" style={inputStyle} />
                            <button onClick={quickAddTopics} disabled={topicsAdding || !quickTopics.trim()}
                              className="text-xs px-3 py-2 rounded disabled:opacity-50 shrink-0"
                              style={{ background: topicsAdded ? "#22c55e" : "var(--accent)", color: "#fff" }}>
                              {topicsAdding ? "…" : topicsAdded ? "✓" : "导入"}
                            </button>
                          </div>
                        </div>
                      </div>

                      <div>
                        <div className="flex items-center gap-2 mb-3">
                          <p className="text-xs font-medium flex-1" style={{ color: "var(--muted)" }}>选题列表</p>
                          {(["unused", "all", "used"] as const).map(f => (
                            <button key={f} onClick={() => setTopicFilter(f)}
                              className="text-xs px-2.5 py-1 rounded-full"
                              style={{
                                background: topicFilter === f ? "var(--accent)" : "var(--surface)",
                                color: topicFilter === f ? "#fff" : "var(--muted)",
                                border: "1px solid var(--border)",
                              }}>
                              {f === "all" ? "全部" : f === "unused" ? "未用" : "已用"}
                            </button>
                          ))}
                        </div>
                        {topicsLoading ? (
                          <p className="text-xs py-5 text-center" style={{ color: "var(--muted)" }}>加载中…</p>
                        ) : topicList.length === 0 ? (
                          <p className="text-xs py-5 text-center" style={{ color: "var(--muted)" }}>暂无选题</p>
                        ) : (
                          <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                            {topicList.map(t => (
                              <div key={t.id} className="flex items-center gap-2 px-3 py-2.5 rounded"
                                style={{ background: "var(--surface)", border: "1px solid var(--border)", opacity: t.is_used ? 0.45 : 1 }}>
                                <span className="flex-1 text-sm leading-snug">{t.content}</span>
                                {t.is_used && <span className="text-xs shrink-0" style={{ color: "var(--muted)" }}>已用</span>}
                                <button onClick={() => deleteTopic(t.id)} className="shrink-0 text-xs" style={{ color: "var(--muted)" }}>×</button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 文案预设 */}
                  {activeTab === "copy" && (
                    <div className="space-y-6">
                      <div className="grid grid-cols-2 gap-x-6 gap-y-5">
                        <div><Label>语气风格</Label><div className="flex flex-wrap gap-2">{TONE_OPTIONS.map(t => <Chip key={t} label={t} active={tone === t} onClick={() => setTone(t)} />)}</div></div>
                        <div><Label>开场方式</Label><div className="flex flex-wrap gap-2">{OPENING_STYLES.map(s => <Chip key={s} label={s} active={openingStyle === s} onClick={() => setOpeningStyle(s)} />)}</div></div>
                        <div><Label>行文格式</Label><div className="flex flex-wrap gap-2">{FORMAT_STYLES.map(s => <Chip key={s} label={s} active={formatStyle === s} onClick={() => setFormatStyle(s)} />)}</div></div>
                        <div className="space-y-4">
                          <div><Label>Emoji 用量</Label><div className="flex gap-2">{EMOJI_OPTIONS.map(e => <Chip key={e} label={e} active={emojiUsage === e} onClick={() => setEmojiUsage(e)} />)}</div></div>
                          <div><Label>正文字数</Label><div className="flex gap-2">{LENGTH_OPTIONS.map(l => <Chip key={l} label={l} active={contentLength === l} onClick={() => setContentLength(l)} />)}</div></div>
                        </div>
                      </div>

                      <div className="grid grid-cols-2 gap-x-6 gap-y-5">
                        <div>
                          <Label>禁止词汇</Label>
                          <div className="flex flex-wrap gap-1.5 mb-2 min-h-7">
                            {forbidden.map((w, i) => (
                              <span key={i} className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded"
                                style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                                {w}<button onClick={() => setForbidden(prev => prev.filter((_, idx) => idx !== i))} style={{ color: "var(--muted)" }}>×</button>
                              </span>
                            ))}
                          </div>
                          <input value={newForbidden} onChange={e => setNewForbidden(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter" && newForbidden.trim()) { setForbidden(p => [...p, newForbidden.trim()]); setNewForbidden(""); } }}
                            placeholder="输入禁词，回车添加" className="w-full text-sm px-3 py-2.5 rounded" style={inputStyle} />
                        </div>
                      </div>

                      <div>
                        <Label>文案提示词模板</Label>

                        {/* 内容类型切换：选哪个类型就编辑哪个的提示词 */}
                        {contentTypes.length > 1 && (
                          <div className="flex flex-wrap gap-1.5 mb-3">
                            {contentTypes.map(ct => (
                              <button key={ct.id}
                                onClick={() => { setPromptTypeId(ct.id); setPromptTemplate(ct.prompt_template || DEFAULT_PROMPT); }}
                                className="text-xs px-3 py-1.5 rounded transition-colors"
                                style={{
                                  background: promptTypeId === ct.id ? "color-mix(in srgb, var(--accent) 12%, var(--background))" : "var(--surface)",
                                  border: `1px solid ${promptTypeId === ct.id ? "var(--accent)" : "var(--border)"}`,
                                  color: promptTypeId === ct.id ? "var(--accent)" : "var(--foreground)",
                                }}>
                                {ct.name}
                              </button>
                            ))}
                          </div>
                        )}

                        <div className="mb-2 rounded text-xs overflow-hidden"
                          style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                          <div className="px-3 py-1.5 font-semibold" style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>可用变量</div>
                          <table className="w-full table-fixed">
                            <colgroup>
                              <col style={{ width: "42%" }} />
                              <col style={{ width: "58%" }} />
                            </colgroup>
                            <tbody>
                              {([
                                { key: "{niche}",                desc: "账号方向",   val: niche || "" },
                                { key: "{target_audience}",      desc: "目标受众",   val: audience || "" },
                                { key: "{topic}",                desc: "选题",       val: "" },
                                { key: "{content_type}",         desc: "内容类型",   val: "" },
                                { key: "{tone}",                 desc: "语气风格",   val: tone || "" },
                                { key: "{competitive_advantage}", desc: "差异化优势", val: advantage || "" },
                                { key: "{opening_style}",        desc: "开场方式",   val: openingStyle || "" },
                                { key: "{format_style}",         desc: "行文格式",   val: formatStyle || "" },
                                { key: "{emoji_usage}",          desc: "Emoji 用量", val: emojiUsage || "" },
                                { key: "{content_length}",       desc: "正文字数",   val: contentLength || "" },
                                { key: "{pain_points}",          desc: "受众痛点",   val: painPoints.join(" / ") },
                                { key: "{forbidden_words}",      desc: "禁止词汇",   val: forbidden.join(" ") },
                                { key: "{content_pillars}",      desc: selectedPillar ? `内容方向（已选：${selectedPillar}）` : "内容方向（全部）", val: selectedPillar ? (pillars.find(p => p.name === selectedPillar)?.description ? `${selectedPillar}（${pillars.find(p => p.name === selectedPillar)!.description}）` : selectedPillar) : pillars.map(p => p.name).join("、") },
                              ] as { key: string; desc: string; val: string }[]).map(p => {
                                const isDynamic = p.key === "{topic}" || p.key === "{content_type}";
                                return (
                                  <tr key={p.key} style={{ borderBottom: "1px solid var(--border)" }}>
                                    <td className="px-3 py-1.5 whitespace-nowrap">
                                      <code style={{ color: "var(--accent)" }}>{p.key}</code>
                                      <span className="ml-2" style={{ color: "var(--muted)" }}>{p.desc}</span>
                                    </td>
                                    <td className="px-3 py-1.5 truncate" title={p.val || undefined}>
                                      {isDynamic
                                        ? <span style={{ color: "var(--muted)", fontStyle: "italic" }}>运行时注入</span>
                                        : p.val
                                          ? <span>{p.val}</span>
                                          : <span style={{ color: "var(--muted)", fontStyle: "italic" }}>未设置</span>}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        <textarea value={promptTemplate} onChange={e => setPromptTemplate(e.target.value)}
                          rows={12} className="w-full text-xs px-3 py-2.5 rounded resize-y font-mono leading-relaxed" style={inputStyle} />
                        <button onClick={() => setShowPromptPreview(v => !v)}
                          className="mt-2 text-xs px-3 py-1.5 rounded"
                          style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                          {showPromptPreview ? "▲ 收起预览" : "▼ 预览完整 Prompt"}
                        </button>
                        {showPromptPreview && (
                          <pre className="mt-2 text-xs p-4 rounded whitespace-pre-wrap leading-relaxed overflow-auto"
                            style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--foreground)", maxHeight: 360 }}>
                            {buildPromptPreview()}
                          </pre>
                        )}
                      </div>

                      <SaveBtn saving={copySaving} saved={copySaved} onClick={saveCopyStrategy} label="保存文案预设" />
                    </div>
                  )}

                  {/* 图片预设 */}
                  {activeTab === "image" && (
                    <div className="space-y-6">
                      <div>
                        <Label>生成模式</Label>
                        <div className="grid grid-cols-3 gap-3">
                          {IMG_MODES.map(m => (
                            <button key={m.value} onClick={() => setImgMode(m.value)}
                              className="text-left px-4 py-3 rounded"
                              style={{
                                background: imgMode === m.value ? "color-mix(in srgb, var(--accent) 8%, var(--background))" : "var(--surface)",
                                border: `1px solid ${imgMode === m.value ? "var(--accent)" : "var(--border)"}`,
                              }}>
                              <p className="text-sm font-medium" style={{ color: imgMode === m.value ? "var(--accent)" : "var(--foreground)" }}>{m.label}</p>
                              <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>{m.desc}</p>
                            </button>
                          ))}
                        </div>
                      </div>

                      {(imgMode === "cards" || imgMode === "both") && (
                        <div>
                          <Label>卡片配色主题</Label>
                          <div className="grid grid-cols-7 gap-2">
                            {CARD_THEMES.map(t => (
                              <MiniTheme key={t.value} theme={t} selected={cardTheme === t.value} onClick={() => setCardTheme(t.value)} />
                            ))}
                          </div>
                          <button onClick={() => setCardTheme("random")}
                            className="mt-3 w-full rounded overflow-hidden text-left"
                            style={{ border: `2px solid ${cardTheme === "random" ? "var(--accent)" : "var(--border)"}` }}>
                            <div className="flex items-center gap-3 px-4 py-2.5"
                              style={{ background: "linear-gradient(135deg,#3450E4 0%,#FF2442 30%,#43e97b 60%,#fa709a 100%)" }}>
                              <div className="flex gap-0.5">
                                {["#3450E4","#FF2442","#43e97b","#fa709a","#1a1a2e"].map((c, i) => (
                                  <div key={i} className="w-3 h-3 rounded-full border border-white/50" style={{ background: c, marginLeft: i > 0 ? -4 : 0 }} />
                                ))}
                              </div>
                              <p className="text-xs font-semibold text-white flex-1">每次随机</p>
                              {cardTheme === "random" && (
                                <div className="w-4 h-4 rounded-full flex items-center justify-center font-bold"
                                  style={{ background: "var(--accent)", color: "#fff", fontSize: 9 }}>✓</div>
                              )}
                            </div>
                          </button>
                        </div>
                      )}

                      {(imgMode === "ai" || imgMode === "both") && templates.length === 0 && (
                        <div>
                          <Label>图片提示词</Label>
                          <div className="mb-2 rounded text-xs overflow-hidden"
                            style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                            <div className="px-3 py-1 font-semibold" style={{ color: "var(--muted)", borderBottom: "1px solid var(--border)" }}>可用变量</div>
                            <table className="w-full">
                              <tbody>
                                {([
                                  { key: "{niche}", desc: "账号方向", val: niche || "（未设置）" },
                                  { key: "{title}", desc: "文案标题", val: "运行时由 AI 生成的标题决定" },
                                ] as { key: string; desc: string; val: string }[]).map(p => (
                                  <tr key={p.key} style={{ borderBottom: "1px solid var(--border)" }}>
                                    <td className="px-3 py-1 w-28 font-mono"><code style={{ color: "var(--accent)" }}>{p.key}</code></td>
                                    <td className="px-3 py-1 w-24" style={{ color: "var(--muted)" }}>{p.desc}</td>
                                    <td className="px-3 py-1">
                                      {p.val.startsWith("运行时") || p.val === "（未设置）"
                                        ? <span style={{ color: "var(--muted)", fontStyle: "italic" }}>{p.val}</span>
                                        : <span className="font-medium">{p.val}</span>}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <textarea value={imgPrompt} onChange={e => setImgPrompt(e.target.value)}
                            placeholder={"小红书封面图，{niche}领域，主题：{title}"}
                            rows={4} className="w-full text-sm px-3 py-2.5 rounded resize-none"
                            style={inputStyle} />
                        </div>
                      )}

                      {/* AI 图片模板：只在涉及 AI 生图的模式下显示 */}
                      {(imgMode === "ai" || imgMode === "both") && <div>
                        <Label>AI 图片模板</Label>

                        {/* 随机 / 指定 切换 */}
                        <div className="flex gap-2 mb-3">
                          {(["specific", "random"] as const).map(m => (
                            <button key={m} onClick={() => setTemplateMode(m)}
                              className="flex-1 text-xs py-1.5 rounded transition-colors"
                              style={{
                                background: templateMode === m ? "color-mix(in srgb, var(--accent) 12%, var(--background))" : "var(--surface)",
                                border: `1px solid ${templateMode === m ? "var(--accent)" : "var(--border)"}`,
                                color: templateMode === m ? "var(--accent)" : "var(--muted)",
                              }}>
                              {m === "specific" ? "指定模板" : "🎲 随机模板"}
                            </button>
                          ))}
                        </div>
                        <p className="text-xs mb-3" style={{ color: "var(--muted)" }}>
                          {templateMode === "random"
                            ? "每次生成随机从下方模板中选一套，视觉风格多样。"
                            : "每次生成使用激活的模板，风格固定统一。"}
                        </p>

                        {templateMode === "specific" && templates.find(t => t.is_active) && (
                          <div className="flex items-center gap-2 py-2 px-3 rounded mb-3"
                            style={{ background: "color-mix(in srgb, var(--accent) 10%, transparent)", border: "1px solid var(--accent)" }}>
                            <span className="text-xs flex-1">当前使用模板：<strong>{templates.find(t => t.is_active)?.name}</strong></span>
                            <button onClick={deactivateTemplate}
                              className="text-xs px-2 py-0.5 rounded" style={{ border: "1px solid var(--border)", color: "var(--muted)" }}>
                              取消激活
                            </button>
                          </div>
                        )}

                        <div className="space-y-2">
                          {templates.map(tpl => (
                            <TemplateCard key={tpl.id} tpl={tpl} accountId={accId}
                              onActivate={templateMode === "specific" ? () => activateTemplate(tpl.id) : undefined}
                              onEdit={() => setEditingTpl(tpl)}
                              onDelete={() => deleteTemplate(tpl.id)} />
                          ))}
                          {templates.length === 0 && (
                            <p className="text-xs py-3 text-center" style={{ color: "var(--muted)" }}>暂无模板，点击下方新建</p>
                          )}
                        </div>

                        <button onClick={() => setEditingTpl({})}
                          className="mt-3 text-xs px-4 py-2 rounded w-full"
                          style={{ border: "1px dashed var(--border)", color: "var(--muted)" }}>
                          + 新建模板
                        </button>
                      </div>}

                      <SaveBtn saving={imgSaving} saved={imgSaved} onClick={saveImageStrategy} label="保存图片预设" />
                    </div>
                  )}

                </div>
              </div>

              {/* 右栏：本次生成 */}
              <div className="col-span-2 space-y-3">
                <div className="rounded-lg p-5 space-y-5"
                  style={{ background: "var(--background)", border: "1px solid var(--border)" }}>
                  <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>本次生成</p>

                  <div>
                    <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>选题来源</p>
                    <div className="space-y-1.5">
                      {[
                        { value: "auto",   label: "自动取题", desc: "从选题库顺序消费" },
                        { value: "manual", label: "手动输入", desc: "临时指定，不消耗库" },
                        { value: "pick",   label: "从库挑选", desc: "手动选一条" },
                      ].map(opt => (
                        <button key={opt.value} onClick={() => setTopicMode(opt.value as "auto" | "manual" | "pick")}
                          className="w-full text-sm px-3 py-2 rounded text-left"
                          style={radioStyle(topicMode === opt.value)}>
                          <span className="font-medium">{opt.label}</span>
                          <span className="text-xs ml-2" style={{ color: "var(--muted)" }}>{opt.desc}</span>
                        </button>
                      ))}
                    </div>

                    {topicMode === "manual" && (
                      <textarea value={manualTopic} onChange={e => setManualTopic(e.target.value)}
                        placeholder="输入选题，例如：被裁员后我做的第一件事"
                        rows={2} className="w-full text-sm px-3 py-2 rounded resize-none mt-2" style={inputStyle} />
                    )}

                    {topicMode === "pick" && (
                      <div className="space-y-1 max-h-40 overflow-y-auto mt-2">
                        {topicsLoading ? (
                          <p className="text-xs py-3 text-center" style={{ color: "var(--muted)" }}>加载中…</p>
                        ) : topicList.length === 0 ? (
                          <p className="text-xs py-3 text-center" style={{ color: "var(--muted)" }}>选题库暂无未用选题</p>
                        ) : topicList.map(t => (
                          <button key={t.id} onClick={() => setPickedTopic(t)}
                            className="w-full text-left text-xs px-3 py-2 rounded leading-snug"
                            style={{
                              background: pickedTopic?.id === t.id ? "color-mix(in srgb, var(--accent) 8%, var(--background))" : "var(--surface)",
                              border: `1px solid ${pickedTopic?.id === t.id ? "var(--accent)" : "var(--border)"}`,
                              color: pickedTopic?.id === t.id ? "var(--accent)" : "var(--foreground)",
                            }}>
                            {t.content}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {pillars.length > 0 && (
                    <div>
                      <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>内容方向</p>
                      <div className="flex flex-wrap gap-1.5">
                        <Chip label="自动" active={selectedPillar === ""} onClick={() => setSelectedPillar("")} />
                        {pillars.map(p => (
                          <Chip key={p.name} label={p.name} active={selectedPillar === p.name} onClick={() => setSelectedPillar(p.name)} />
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>图片模式</p>
                    <div className="flex flex-wrap gap-1.5">
                      {IMG_MODES.map(m => (
                        <Chip key={m.value} label={m.label} active={imageMode === m.value as ImageMode} onClick={() => setImageMode(m.value as ImageMode)} />
                      ))}
                    </div>
                  </div>

                  {(generating || genSuccess) && (
                    <div className="flex items-center justify-between gap-1">
                      {GEN_STEPS.map((step, i) => {
                        const done = genSuccess ? true : genStep > i;
                        const current = !genSuccess && genStep === i;
                        return (
                          <div key={step.key} className="flex-1 flex flex-col items-center gap-1">
                            <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
                              style={{ background: done ? "#22c55e" : current ? "var(--accent)" : "var(--border)", color: done || current ? "#fff" : "var(--muted)" }}>
                              {done ? "✓" : current ? <span className="animate-spin inline-block">·</span> : i + 1}
                            </div>
                            <p className="text-xs text-center leading-tight"
                              style={{ color: done ? "#22c55e" : current ? "var(--accent)" : "var(--muted)", fontWeight: current ? 600 : 400 }}>
                              {step.label}
                            </p>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <button onClick={generate} disabled={generating}
                    className="w-full py-3 rounded text-sm font-medium disabled:opacity-60"
                    style={{ background: genSuccess ? "#22c55e" : "var(--accent)", color: "#fff" }}>
                    {generating ? `${GEN_STEPS[genStep]?.label}…` : genSuccess ? "✓ 已推送飞书" : "开始生成"}
                  </button>

                  {genError && !generating && (
                    <p className="text-xs text-center" style={{ color: "var(--accent)" }}>{genError}</p>
                  )}
                  {generating && (
                    <p className="text-xs text-center animate-pulse" style={{ color: "var(--muted)" }}>
                      图片生成可能需要 20-60 秒
                    </p>
                  )}
                </div>
              </div>

            </div>
          )}
        </div>
      )}

      {editingTpl !== false && (
        <TemplateEditor
          initial={editingTpl}
          accountId={accId}
          onSave={saveTemplate}
          onCancel={() => setEditingTpl(false)} />
      )}
    </div>
  );
}
