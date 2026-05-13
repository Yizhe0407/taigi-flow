"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentProfile } from "@taigi-flow/db";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

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

  const [form, setForm] = useState<FormState>(profile ? profileToForm(profile) : DEFAULT);
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
        tools: form.tools.split(",").map((s) => s.trim()).filter(Boolean),
        isActive: form.isActive,
      };

      const url = isEdit ? `/api/agent-profiles/${profile.id}` : "/api/agent-profiles";
      const res = await fetch(url, {
        method: isEdit ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(typeof data.error === "string" ? data.error : JSON.stringify(data));
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
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Field label="名稱" required htmlFor="name">
          <Input
            id="name"
            required
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </Field>

        <Field label="說明" htmlFor="description">
          <Input
            id="description"
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </Field>

        <Field label="系統提示詞" required htmlFor="systemPrompt">
          <Textarea
            id="systemPrompt"
            required
            rows={8}
            className="font-mono text-sm"
            value={form.systemPrompt}
            onChange={(e) => set("systemPrompt", e.target.value)}
          />
        </Field>

        <fieldset className="border border-border rounded-lg p-4 space-y-3">
          <legend className="text-sm font-medium px-1">語音設定</legend>
          <Field label="Piper 模型" required htmlFor="piperModel">
            <Input
              id="piperModel"
              required
              value={form.piperModel}
              onChange={(e) => set("piperModel", e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="速度" htmlFor="speed">
              <Input
                id="speed"
                type="number"
                step="0.1"
                min="0.5"
                max="2"
                value={form.speed}
                onChange={(e) => set("speed", e.target.value)}
              />
            </Field>
            <Field label="音調" htmlFor="pitch">
              <Input
                id="pitch"
                type="number"
                step="1"
                min="-10"
                max="10"
                value={form.pitch}
                onChange={(e) => set("pitch", e.target.value)}
              />
            </Field>
          </div>
        </fieldset>

        <Field label="工具（逗號分隔）" htmlFor="tools">
          <Input
            id="tools"
            placeholder="tdx.bus_arrival, tdx.bus_route"
            value={form.tools}
            onChange={(e) => set("tools", e.target.value)}
          />
        </Field>

        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <Checkbox
            checked={form.isActive}
            onCheckedChange={(v) => set("isActive", v)}
          />
          啟用此人格
        </label>

        <div className="flex gap-3 pt-2">
          <Button type="submit" disabled={saving}>
            {saving ? "儲存中…" : "儲存"}
          </Button>
          <Button type="button" variant="outline" onClick={() => router.push("/agents")}>
            取消
          </Button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  required,
  htmlFor,
  children,
}: {
  label: string;
  required?: boolean;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>
        {label}
        {required && <span className="text-destructive ml-0.5">*</span>}
      </Label>
      {children}
    </div>
  );
}
