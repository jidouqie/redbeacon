"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

function Toggle({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button onClick={() => !disabled && onChange(!checked)} disabled={disabled}
      className="relative shrink-0 rounded-full transition-colors disabled:opacity-40"
      style={{ width: 40, height: 22, background: checked ? "var(--accent)" : "var(--border)" }}>
      <span className="absolute top-0.5 rounded-full transition-all"
        style={{ width: 18, height: 18, background: "#fff", left: checked ? 20 : 2 }} />
    </button>
  );
}

function Card({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg p-5 space-y-4" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted)" }}>{title}</p>
        {hint && <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>{hint}</p>}
      </div>
      {children}
    </div>
  );
}

export default function AutomationPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);

  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [jobs, setJobs] = useState<Array<{ id: string; name: string; next_run: string }>>([]);

  const [autoGenerate, setAutoGenerate]       = useState(true);
  const [autoPublish, setAutoPublish]         = useState(true);
  const [publishInterval, setPublishInterval] = useState(15);

  const refresh = useCallback(async () => {
    const [conf, status] = await Promise.all([
      api.automation.config().catch(() => null),
      api.automation.status().catch(() => null),
    ]);
    if (conf) {
      setAutoGenerate(conf.auto_generate_enabled !== "false");
      setAutoPublish(conf.auto_publish_enabled !== "false");
      setPublishInterval(parseInt(conf.publish_interval_minutes) || 15);
    }
    if (status) {
      setSchedulerRunning(status.running);
      setJobs(status.jobs);
    }
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function saveAll() {
    setSaving(true); setSaved(false);
    try {
      await api.automation.updateConfig({
        auto_generate_enabled:    autoGenerate,
        auto_publish_enabled:     autoPublish,
        publish_interval_minutes: publishInterval,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      await refresh();
    } catch (e: unknown) {
      alert("保存失败：" + (e instanceof Error ? e.message : String(e)));
    } finally { setSaving(false); }
  }

  if (loading) return <p className="text-sm mt-4" style={{ color: "var(--muted)" }}>加载中…</p>;

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold">自动化</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="space-y-5">

          {/* 调度器状态 */}
          <Card title="调度器状态">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full shrink-0"
                style={{ background: schedulerRunning ? "var(--success)" : "var(--muted)" }} />
              <span className="text-sm">{schedulerRunning ? "运行中" : "已停止"}</span>
            </div>
            {jobs.length > 0 && (
              <div className="rounded overflow-hidden text-xs" style={{ border: "1px solid var(--border)" }}>
                <div className="grid grid-cols-2 px-3 py-2 font-medium"
                  style={{ background: "var(--background)", borderBottom: "1px solid var(--border)", color: "var(--muted)" }}>
                  <span>任务</span><span>下次执行</span>
                </div>
                {jobs.map(j => (
                  <div key={j.id} className="grid grid-cols-2 px-3 py-2"
                    style={{ borderBottom: "1px solid var(--border)", color: "var(--foreground)" }}>
                    <span>{j.name}</span>
                    <span style={{ color: "var(--muted)" }}>{j.next_run}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* 自动生成（全局开关） */}
          <Card title="自动生成" hint="主开关。关闭后所有账号的生成任务均停止，不论账号自身设置。生成排期在各账号管理中单独配置。">
            <div className="flex items-center justify-between">
              <p className="text-sm">全局开启自动生成</p>
              <Toggle checked={autoGenerate} onChange={setAutoGenerate} />
            </div>
          </Card>

        </div>

        <div className="space-y-5">

          {/* 自动发布 */}
          <Card title="自动发布" hint="飞书中审核通过的内容，按以下间隔自动发布到小红书。">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm">开启自动发布</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>关闭后仍可在总览页手动触发</p>
              </div>
              <Toggle checked={autoPublish} onChange={setAutoPublish} />
            </div>
            <div className="flex items-center gap-3">
              <label className="text-sm shrink-0" style={{ color: autoPublish ? "var(--foreground)" : "var(--muted)" }}>
                轮询间隔
              </label>
              <input type="number" min={5} max={120} value={publishInterval}
                onChange={e => setPublishInterval(Math.max(5, parseInt(e.target.value) || 15))}
                disabled={!autoPublish}
                className="w-20 text-sm px-2 py-1.5 rounded text-center disabled:opacity-40"
                style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--foreground)" }} />
              <span className="text-sm" style={{ color: "var(--muted)" }}>分钟（最少 5 分钟）</span>
            </div>
          </Card>

          {/* 说明 */}
          <div className="rounded-lg p-4 text-xs space-y-1" style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--muted)" }}>
            <p className="font-medium" style={{ color: "var(--foreground)" }}>生成排期在账号管理中配置</p>
            <p>每个账号可独立设置：开关、每周频率、固定间隔或指定时间点。</p>
            <p>修改账号排期后调度器会自动重建该账号的任务。</p>
          </div>

          {/* 保存 */}
          <div className="flex justify-end">
            <button onClick={saveAll} disabled={saving}
              className="px-6 py-2 rounded text-sm disabled:opacity-50"
              style={{ background: saved ? "#22c55e" : "var(--accent)", color: "#fff" }}>
              {saving ? "保存中…" : saved ? "✓ 已保存" : "保存配置"}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
