"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentProfile } from "@taigi-flow/db";

type FormState = {
  name: string;
  description: string;
  systemPrompt: string;
  piperModel: string;
  speed: string;
  pitch: string;
  tools: string;
  isActive: boolean;
};

function profileToForm(p: AgentProfile): FormState {
  const vc = p.voiceConfig as { piperModel: string; speed: number; pitch: number };
  return {
    name: p.name,
    description: p.description ?? "",
    systemPrompt: p.systemPrompt,
    piperModel: vc.piperModel ?? "taigi-default",
    speed: String(vc.speed ?? 1),
    pitch: String(vc.pitch ?? 0),
    tools: ((p.tools as string[]) ?? []).join(", "),
    isActive: p.isActive,
  };
}

const DEFAULT: FormState = {
  name: "",
  description: "",
  systemPrompt: "",
  piperModel: "taigi-default",
  speed: "1",
  pitch: "0",
  tools: "",
  isActive: true,
};

export default function AgentForm({ profile }: { profile?: AgentProfile }) {
  const router = useRouter();
  const isEdit = !!profile;

  const [form, setForm] = useState<FormState>(
    profile ? profileToForm(profile) : DEFAULT,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(key: keyof FormState, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = {
        name: form.name,
        description: form.description || null,
        systemPrompt: form.systemPrompt,
        voiceConfig: {
          piperModel: form.piperModel,
          speed: parseFloat(form.speed) || 1,
          pitch: parseFloat(form.pitch) || 0,
        },
        tools: form.tools
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        isActive: form.isActive,
      };

      const url = isEdit
        ? `/api/agent-profiles/${profile.id}`
        : "/api/agent-profiles";
      const res = await fetch(url, {
        method: isEdit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(
          typeof data.error === "string" ? data.error : JSON.stringify(data),
        );
      }

      router.push("/agents");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold mb-6">{isEdit ? "編輯人格" : "新增人格"}</h1>

      <form onSubmit={submit} className="space-y-5">
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {error}
          </div>
        )}

        <Field label="名稱" required>
          <input
            required
            className="input"
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </Field>

        <Field label="說明">
          <input
            className="input"
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </Field>

        <Field label="系統提示詞" required>
          <textarea
            required
            rows={8}
            className="input font-mono text-sm"
            value={form.systemPrompt}
            onChange={(e) => set("systemPrompt", e.target.value)}
          />
        </Field>

        <fieldset className="border border-gray-200 rounded p-4 space-y-3">
          <legend className="text-sm font-medium px-1">語音設定</legend>
          <Field label="Piper 模型" required>
            <input
              required
              className="input"
              value={form.piperModel}
              onChange={(e) => set("piperModel", e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="速度">
              <input
                type="number"
                step="0.1"
                min="0.5"
                max="2"
                className="input"
                value={form.speed}
                onChange={(e) => set("speed", e.target.value)}
              />
            </Field>
            <Field label="音調">
              <input
                type="number"
                step="1"
                min="-10"
                max="10"
                className="input"
                value={form.pitch}
                onChange={(e) => set("pitch", e.target.value)}
              />
            </Field>
          </div>
        </fieldset>

        <Field label="工具（逗號分隔）">
          <input
            className="input"
            placeholder="tdx.bus_arrival, tdx.bus_route"
            value={form.tools}
            onChange={(e) => set("tools", e.target.value)}
          />
        </Field>

        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={form.isActive}
            onChange={(e) => set("isActive", e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-indigo-600"
          />
          啟用此人格
        </label>

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="px-5 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? "儲存中…" : "儲存"}
          </button>
          <button
            type="button"
            onClick={() => router.push("/agents")}
            className="px-5 py-2 bg-white border border-gray-300 text-sm rounded hover:bg-gray-50"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {children}
    </div>
  );
}
