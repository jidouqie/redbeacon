// API 客户端 — 所有请求走 Next.js rewrites 代理到 :8000

export interface Account {
  id: number;
  display_name: string | null;
  nickname: string | null;
  xhs_user_id: string | null;
  login_status: string;
  mcp_port: number;
  mcp_running: boolean;
  mcp_headless: boolean;
  proxy: string | null;
  last_login_check: string | null;
  feishu_app_token: string | null;
  feishu_table_id: string | null;
  feishu_user_id: string | null;
  auto_generate_enabled: boolean;
  generate_schedule_json: string | null;
}

export interface Strategy {
  id: number;
  account_id: number;
  version: number;
  data: string; // JSON string
  niche: string;
  posting_freq: string;
  created_at: string;
  updated_at: string;
}

export interface ContentItem {
  id: number;
  account_id: number;
  topic: string;
  content_type: string | null;
  pillar_name: string | null;
  title: string;
  body: string;
  tags: string[];
  image_prompt: string | null;
  images: string[];
  visual_theme: string | null;
  status: string;
  error_msg: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  xhs_note_id: string | null;
  created_at: string;
}

export interface ContentType {
  id: number;
  name: string;
  prompt_template: string;
  is_active: boolean;
  sort_order: number;
}

export interface Topic {
  id: number;
  content_type: string;
  content: string;
  is_used: boolean;
  used_at: string | null;
  created_at: string;
}

export interface TopicStats {
  total: number;
  unused: number;
  used: number;
  by_type: Array<{ content_type: string; total: number; unused: number }>;
}

export interface Prompt {
  id: number;
  account_id: number;
  type: string;
  name: string;
  prompt_text: string;
  is_active: boolean;
  version: number;
}

export interface ImageStrategy {
  mode: string;           // "cards" | "ai" | "both" | "none"
  prompt_template: string;
  card_theme: string;
  reference_images: string[];
  ai_model: string | null;
  template_mode: string;  // "specific" | "random"
}

export interface ImageTemplateItem {
  image_path: string;  // 本地绝对路径 或 data:image/... 或空字符串
  prompt: string;
}

export interface ImageTemplate {
  id: number;
  account_id: number;
  name: string;
  is_active: boolean;
  items: ImageTemplateItem[];
  created_at: string;
  updated_at: string;
}

// PATCH /api/strategy/{id} 接受任意字段，直接合并到 data JSON
export type StrategyEditFields = Record<string, unknown>;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    throw new Error(typeof detail === "object" ? JSON.stringify(detail) : detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── 账号 ──────────────────────────────────────────────────────────────────────

export const api = {
  accounts: {
    list: () => request<Account[]>("/api/accounts"),
    get: (id: number) => request<Account>(`/api/accounts/${id}`),
    create: (body?: { proxy?: string; mcp_port?: number }) =>
      request<Account>("/api/accounts", { method: "POST", body: JSON.stringify(body ?? {}) }),
    delete: (id: number) =>
      request<void>(`/api/accounts/${id}`, { method: "DELETE" }),
    loginStart: (id: number) =>
      request<{ ok: boolean; port: number }>(`/api/accounts/${id}/login/start`, { method: "POST" }),
    loginQr: (id: number) =>
      request<{ img?: string; timeout?: number; already_logged_in: boolean }>(`/api/accounts/${id}/login/qr`),
    loginStatus: (id: number) =>
      request<{ logged_in: boolean; nickname?: string; error?: string }>(`/api/accounts/${id}/login/status`),
    logout: (id: number) =>
      request<{ ok: boolean }>(`/api/accounts/${id}/login`, { method: "DELETE" }),
    mcpStart: (id: number) =>
      request<{ pid: number; port: number }>(`/api/accounts/${id}/mcp/start`, { method: "POST" }),
    mcpStop: (id: number) =>
      request<{ ok: boolean }>(`/api/accounts/${id}/mcp/stop`, { method: "POST" }),
    mcpStatus: (id: number) => request<{ running: boolean }>(`/api/accounts/${id}/mcp/status`),
    mcpLogs: (id: number, tail?: number) =>
      request<{ lines: string[] }>(`/api/accounts/${id}/mcp/logs${tail ? `?tail=${tail}` : ""}`),
    verifyLogin: (id: number) =>
      request<{ logged_in: boolean; nickname?: string; error?: string }>(`/api/accounts/${id}/login/verify`),
    update: (id: number, body: { display_name?: string; proxy?: string; feishu_app_token?: string; feishu_table_id?: string; feishu_user_id?: string; mcp_headless?: boolean; auto_generate_enabled?: boolean; generate_schedule_json?: string }) =>
      request<Account>(`/api/accounts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    feishuSetup: (id: number, body?: { app_token?: string; table_id?: string }) =>
      request<{ tenant_token_ok: boolean; app_token?: string; table_id?: string; saved?: boolean }>(
        `/api/accounts/${id}/feishu/setup`, { method: "POST", body: JSON.stringify(body ?? {}) }),
    feishuTest: (id: number) =>
      request<{ table_write: string; table_delete: string; message: string }>(`/api/accounts/${id}/feishu/test`, { method: "POST" }),
  },

  // ── 内容 ────────────────────────────────────────────────────────────────────

  content: {
    list: (accountId: number, status?: string) => {
      const qs = status ? `?status=${status}` : "";
      return request<ContentItem[]>(`/api/content/${accountId}${qs}`);
    },
    pending: (accountId: number) => request<ContentItem[]>(`/api/content/${accountId}/pending`),
    get: (accountId: number, itemId: number) =>
      request<ContentItem>(`/api/content/${accountId}/item/${itemId}`),
    setStatus: (accountId: number, itemId: number, status: string) =>
      request<{ ok: boolean }>(`/api/content/${accountId}/item/${itemId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      }),
    update: (accountId: number, itemId: number, fields: { title?: string; body?: string; tags?: string[] }) =>
      request<ContentItem>(`/api/content/${accountId}/item/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(fields),
      }),
    feishuSync: () =>
      request<{ ok: boolean; synced: number }>("/api/content/feishu-sync", { method: "POST" }),
    publishNow: () =>
      request<{ ok: boolean; synced: number; published: number }>("/api/content/publish-now", { method: "POST" }),
    feishuUrl: () =>
      request<{ url: string | null }>("/api/content/feishu-url"),
    publishRunning: () =>
      request<{ running: boolean }>("/api/content/publish-running"),
    cancelPublish: () =>
      request<{ ok: boolean; cancelled: boolean; msg: string }>("/api/content/cancel-publish", { method: "POST" }),
    generate: (accountId: number, opts?: { topic?: string; content_type?: string; image_mode?: string; pillar?: string }) =>
      request<{ job_id: string }>(`/api/content/${accountId}/generate`, {
        method: "POST",
        body: JSON.stringify(opts ?? {}),
      }),
    pollJob: (jobId: string) =>
      request<{ step: number; status: string; content_id: number | null; error: string | null }>(
        `/api/content/jobs/${jobId}`
      ),
  },

  // ── 策略 ────────────────────────────────────────────────────────────────────

  strategy: {
    get: (accountId: number) => request<Strategy>(`/api/strategy/${accountId}`),
    prompts: (accountId: number) => request<Prompt[]>(`/api/strategy/${accountId}/prompts`),
    addPrompt: (accountId: number, body: { type: string; name: string; prompt_text: string; notes?: string }) =>
      request<Prompt>(`/api/strategy/${accountId}/prompts`, { method: "POST", body: JSON.stringify(body) }),
    updatePrompt: (accountId: number, promptId: number, body: { prompt_text: string; notes?: string }) =>
      request<Prompt>(`/api/strategy/${accountId}/prompts/${promptId}`, { method: "PUT", body: JSON.stringify(body) }),
    edit: (accountId: number, fields: StrategyEditFields) =>
      request<{ ok: boolean }>(`/api/strategy/${accountId}`, {
        method: "PATCH",
        body: JSON.stringify(fields),
      }),
    getImage: (accountId: number) =>
      request<ImageStrategy>(`/api/strategy/${accountId}/image`),
    updateImage: (accountId: number, body: ImageStrategy) =>
      request<{ ok: boolean }>(`/api/strategy/${accountId}/image`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    listImageTemplates: (accountId: number) =>
      request<ImageTemplate[]>(`/api/strategy/${accountId}/image-templates`),
    createImageTemplate: (accountId: number, body: { name: string; items: ImageTemplateItem[] }) =>
      request<ImageTemplate>(`/api/strategy/${accountId}/image-templates`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    updateImageTemplate: (accountId: number, templateId: number, body: { name: string; items: ImageTemplateItem[] }) =>
      request<ImageTemplate>(`/api/strategy/${accountId}/image-templates/${templateId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteImageTemplate: (accountId: number, templateId: number) =>
      request<{ ok: boolean }>(`/api/strategy/${accountId}/image-templates/${templateId}`, {
        method: "DELETE",
      }),
    activateImageTemplate: (accountId: number, templateId: number) =>
      request<{ ok: boolean }>(`/api/strategy/${accountId}/image-templates/${templateId}/activate`, {
        method: "POST",
      }),
    deactivateImageTemplates: (accountId: number) =>
      request<{ ok: boolean }>(`/api/strategy/${accountId}/image-templates/deactivate`, {
        method: "POST",
      }),
    uploadReferenceImage: async (accountId: number, file: File): Promise<{ path: string; filename: string }> => {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`/api/strategy/${accountId}/upload-image`, { method: "POST", body: fd });
      if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(e.detail); }
      return res.json();
    },
  },

  // ── 选题库 & 内容类型 ─────────────────────────────────────────────────────────

  topics: {
    // 内容类型
    listTypes: (accountId: number) =>
      request<ContentType[]>(`/api/topics/${accountId}/types`),
    initTypes: (accountId: number) =>
      request<ContentType[]>(`/api/topics/${accountId}/types/init`, { method: "POST" }),
    createType: (accountId: number, body: { name: string; prompt_template: string }) =>
      request<ContentType>(`/api/topics/${accountId}/types`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    updateType: (accountId: number, typeId: number, body: Partial<ContentType>) =>
      request<ContentType>(`/api/topics/${accountId}/types/${typeId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    deleteType: (accountId: number, typeId: number) =>
      request<void>(`/api/topics/${accountId}/types/${typeId}`, { method: "DELETE" }),

    // 选题
    stats: (accountId: number) => request<TopicStats>(`/api/topics/${accountId}/stats`),
    list: (accountId: number, contentType?: string, isUsed?: number) => {
      const params = new URLSearchParams();
      if (contentType) params.set("content_type", contentType);
      if (isUsed !== undefined) params.set("is_used", String(isUsed));
      const qs = params.toString() ? `?${params}` : "";
      return request<Topic[]>(`/api/topics/${accountId}${qs}`);
    },
    create: (accountId: number, body: { content_type: string; content: string }) =>
      request<Topic>(`/api/topics/${accountId}`, { method: "POST", body: JSON.stringify(body) }),
    batchImport: (accountId: number, content_type: string, text: string) =>
      request<{ inserted: number; total: number }>(`/api/topics/${accountId}/batch`, {
        method: "POST",
        body: JSON.stringify({ content_type, text }),
      }),
    delete: (accountId: number, topicId: number) =>
      request<void>(`/api/topics/${accountId}/${topicId}`, { method: "DELETE" }),
    reset: (accountId: number, topicId: number) =>
      request<{ ok: boolean }>(`/api/topics/${accountId}/${topicId}/reset`, { method: "POST" }),
    resetAll: (accountId: number, contentType?: string) => {
      const qs = contentType ? `?content_type=${encodeURIComponent(contentType)}` : "";
      return request<{ ok: boolean }>(`/api/topics/${accountId}/reset-all${qs}`, { method: "POST" });
    },
  },

  // ── 自动化 ───────────────────────────────────────────────────────────────────

  automation: {
    status: () => request<{ running: boolean; jobs: Array<{ id: string; name: string; next_run: string }> }>("/api/automation/status"),
    config: () => request<{ auto_generate_enabled: string; auto_publish_enabled: string; publish_interval_minutes: string }>("/api/automation/config"),
    updateConfig: (body: { auto_generate_enabled?: boolean; auto_publish_enabled?: boolean; publish_interval_minutes?: number }) =>
      request<{ ok: boolean }>("/api/automation/config", { method: "PATCH", body: JSON.stringify(body) }),
    trigger: (task: "publish" | "generate") =>
      request<{ ok: boolean; published?: number; generated?: number }>(`/api/automation/trigger/${task}`, { method: "POST" }),
  },

  // ── 调试 ────────────────────────────────────────────────────────────────────

  debug: {
    copy: (body: { account_id: number; topic: string; content_type?: string; prompt_template: string }) =>
      request<{ title: string; body: string; tags: string[]; filled_prompt: string }>("/api/debug/copy", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    image: (body: { account_id: number; title: string; prompt: string; image_path?: string; model?: string }) =>
      request<{ image_url: string; image_path: string; effective_prompt: string }>("/api/debug/image", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  // ── 设置 ────────────────────────────────────────────────────────────────────

  settings: {
    getAll: () => request<Record<string, string>>("/api/settings"),
    set: (key: string, value: string) =>
      request<{ ok: boolean }>(`/api/settings/${key}`, {
        method: "PUT",
        body: JSON.stringify({ key, value }),
      }),
    batch: (items: { key: string; value: string }[]) =>
      request<{ ok: boolean; updated: number }>("/api/settings/batch", {
        method: "POST",
        body: JSON.stringify({ items }),
      }),
    models: () => request<{ models: string[]; raw_keys: string[]; raw: unknown }>("/api/settings/models"),
    testAi: () => request<{ ok: boolean; reply: string; model: string }>("/api/settings/test-ai", { method: "POST" }),
    testImage: () => request<{ ok: boolean; model: string; found_in_list: boolean }>("/api/settings/test-image", { method: "POST" }),
    testFeishuAuth: () => request<{ ok: boolean; msg: string }>("/api/settings/test-feishu-auth", { method: "POST" }),
    feishuUsers: () => request<{ users: Array<{ user_id: string; name: string }> }>("/api/settings/feishu-users"),
    logs: (tail?: number) => request<{ lines: string[] }>(`/api/settings/logs${tail ? `?tail=${tail}` : ""}`),
    pickFile: () => request<{ path: string | null }>("/api/settings/pick-file"),
    pickFolder: () => request<{ path: string | null }>("/api/settings/pick-folder"),
    proxyTest: () =>
      request<{ ok: boolean; proxy: string }>("/api/settings/proxy/test", { method: "POST" }),
  },
};
