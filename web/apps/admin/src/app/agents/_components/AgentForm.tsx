"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { AgentProfile } from "@taigi-flow/db";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/page-header";

type FormState = {
  name: string;
  description: string;
  systemPrompt: string;
  piperModel: string;
  speed: string;
  pitch: string;
  tools: string;
  isActive: boolean;
  ragEnabled: boolean;
  ragTopK: string;
  ragThreshold: string;
};

function profileToForm(p: AgentProfile): FormState {
  const vc = p.voiceConfig as { piperModel: string; speed: number; pitch: number };
  const rc = p.ragConfig as { enabled?: boolean; topK?: number; threshold?: number } | null;
  return {
    name: p.name,
    description: p.description ?? "",
    systemPrompt: p.systemPrompt,
    piperModel: vc.piperModel ?? "taigi-default",
    speed: String(vc.speed ?? 1),
    pitch: String(vc.pitch ?? 0),
    tools: ((p.tools as string[]) ?? []).join(", "),
    isActive: p.isActive,
    ragEnabled: rc?.enabled ?? false,
    ragTopK: String(rc?.topK ?? 3),
    ragThreshold: String(rc?.threshold ?? 0.7),
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
  ragEnabled: false,
  ragTopK: "3",
  ragThreshold: "0.7",
};

export default function AgentForm({ profile }: { profile?: AgentProfile }) {
  const router = useRouter();
  const isEdit = !!profile;

  const [form, setForm] = useState<FormState>(profile ? profileToForm(profile) : DEFAULT);
  const [saving, setSaving] = useState(false);

  function set(key: keyof FormState, value: string | boolean) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
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
        ragConfig: form.ragEnabled
          ? {
              enabled: true,
              collectionId: profile?.id ?? "",
              topK: parseInt(form.ragTopK) || 3,
              threshold: parseFloat(form.ragThreshold) || 0.7,
            }
          : null,
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

      toast.success(isEdit ? "人格已更新" : "人格已建立");
      router.push("/agents");
      router.refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "儲存失敗");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title={isEdit ? "編輯人格" : "新增人格"}
        description={isEdit ? `ID: ${profile.id}` : "建立一個新的 Role 設定"}
      />

      <form onSubmit={submit} className="space-y-5">

        <Card>
          <CardHeader>
            <CardTitle className="text-base">基本資訊</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="名稱" required htmlFor="name">
              <Input id="name" required placeholder="例：公車站長" value={form.name} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="說明" htmlFor="description">
              <Input id="description" placeholder="簡短描述此人格的用途" value={form.description} onChange={(e) => set("description", e.target.value)} />
            </Field>
            <Field label="系統提示詞" required htmlFor="systemPrompt">
              <Textarea id="systemPrompt" required rows={10} className="font-mono text-sm resize-y" placeholder="你是..." value={form.systemPrompt} onChange={(e) => set("systemPrompt", e.target.value)} />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">語音設定</CardTitle>
            <CardDescription>Piper TTS 模型與輸出參數</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="Piper 模型" required htmlFor="piperModel">
              <Input id="piperModel" required value={form.piperModel} onChange={(e) => set("piperModel", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="速度" htmlFor="speed">
                <Input id="speed" type="number" step="0.1" min="0.5" max="2" value={form.speed} onChange={(e) => set("speed", e.target.value)} />
              </Field>
              <Field label="音調" htmlFor="pitch">
                <Input id="pitch" type="number" step="1" min="-10" max="10" value={form.pitch} onChange={(e) => set("pitch", e.target.value)} />
              </Field>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">RAG</CardTitle>
            <CardDescription>每輪對話自動從 RAG 知識庫檢索相關內容</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <Checkbox checked={form.ragEnabled} onCheckedChange={(v) => set("ragEnabled", v)} />
              <span className="text-sm font-medium">啟用 RAG 檢索</span>
            </label>
            {form.ragEnabled && (
              <div className="grid grid-cols-2 gap-4">
                <Field label="Top-K" htmlFor="ragTopK">
                  <Input id="ragTopK" type="number" min="1" max="10" step="1" value={form.ragTopK} onChange={(e) => set("ragTopK", e.target.value)} />
                </Field>
                <Field label="相似度門檻" htmlFor="ragThreshold">
                  <Input id="ragThreshold" type="number" min="0" max="1" step="0.05" value={form.ragThreshold} onChange={(e) => set("ragThreshold", e.target.value)} />
                </Field>
              </div>
            )}
            {isEdit && (
              <p className="text-xs text-muted-foreground">
                <Link href={`/knowledge/${profile.id}`} className="text-primary hover:underline">
                  前往 RAG 上傳文件 →
                </Link>
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">其他設定</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="工具（逗號分隔）" htmlFor="tools">
              <Input id="tools" placeholder="tdx.bus_arrival, tdx.bus_route" value={form.tools} onChange={(e) => set("tools", e.target.value)} />
            </Field>
            <Separator />
            <label className="flex items-start gap-2.5 cursor-pointer">
              <Checkbox checked={form.isActive} onCheckedChange={(v) => set("isActive", v)} className="mt-0.5" />
              <div>
                <p className="text-sm font-medium">啟用此人格</p>
                <p className="text-xs text-muted-foreground">啟用後將替換目前使用中的人格</p>
              </div>
            </label>
          </CardContent>
        </Card>

        <div className="flex gap-3">
          <Button type="submit" disabled={saving}>{saving ? "儲存中…" : "儲存"}</Button>
          <Button type="button" variant="outline" onClick={() => router.push("/agents")}>取消</Button>
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
