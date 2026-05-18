"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentProfile } from "@taigi-flow/db";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/page-header";
import KnowledgeCollection from "../../knowledge/[collectionId]/_components/KnowledgeCollection";

// ─── Types ──────────────────────────────────────────────────────────────────

type FormState = {
  name: string;
  description: string;
  systemPrompt: string;
  tools: string[];
  isActive: boolean;
  ragEnabled: boolean;
  ragTopK: string;
  ragThreshold: string;
};

type Chunk = {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  createdAt: Date | string;
};

type Job = {
  id: string;
  fileName: string;
  filePath: string;
  status: string;
  chunkCount: number;
  error: string | null;
  createdAt: Date | string;
};

type KnowledgeData = {
  initialChunks: Chunk[];
  initialChunksHasMore: boolean;
  initialJobs: Job[];
};

// ─── Tool definitions ────────────────────────────────────────────────────────

const BUS_STATIC_TOOLS = [
  "bus.search_stops",
  "bus.find_routes",
  "bus.list_stops",
  "bus.next_departures",
] as const;

const GEO_TOOLS = [
  "geo.get_location",
  "geo.geocode",
  "geo.route",
  "geo.poi_nearby",
] as const;

type ToolGroup = {
  tools: readonly string[];
  label: string;
  description: string;
};

const TOOL_GROUPS: ToolGroup[] = [
  {
    tools: BUS_STATIC_TOOLS,
    label: "公車查詢",
    description: "站名搜尋、路線查詢、停靠站列表、班次查詢",
  },
  {
    tools: ["tdx.bus_arrival"],
    label: "即時到站（TDX）",
    description: "透過 TDX API 查詢公車即時到站（需設定 TDX_CLIENT_ID / SECRET）",
  },
  {
    tools: GEO_TOOLS,
    label: "地圖功能",
    description: "GPS 定位、路線規劃、附近地點查詢（同步更新 Playground 地圖）",
  },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function profileToForm(p: AgentProfile): FormState {
  const rc = p.ragConfig as { enabled?: boolean; topK?: number; threshold?: number } | null;
  return {
    name: p.name,
    description: p.description ?? "",
    systemPrompt: p.systemPrompt,
    tools: (p.tools as string[]) ?? [],
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
  tools: [],
  isActive: true,
  ragEnabled: false,
  ragTopK: "3",
  ragThreshold: "0.7",
};

// ─── Main component ───────────────────────────────────────────────────────────

export default function AgentForm({
  profile,
  knowledgeData,
}: {
  profile?: AgentProfile;
  knowledgeData?: KnowledgeData;
}) {
  const router = useRouter();
  const isEdit = !!profile;

  const [form, setForm] = useState<FormState>(profile ? profileToForm(profile) : DEFAULT);
  const [saving, setSaving] = useState(false);

  function set(key: keyof FormState, value: string | boolean | string[]) {
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
        voiceConfig: { piperModel: "taigi-default", speed: 1, pitch: 0 },
        ragConfig: isEdit && form.ragEnabled
          ? {
              enabled: true,
              collectionId: profile?.id ?? "",
              topK: parseInt(form.ragTopK) || 3,
              threshold: form.ragThreshold !== "" ? parseFloat(form.ragThreshold) : 0.7,
            }
          : null,
        tools: form.tools,
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
      if (!isEdit) {
        router.push("/agents");
      } else {
        router.refresh();
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "儲存失敗");
    } finally {
      setSaving(false);
    }
  }

  const ragConfig = isEdit && form.ragEnabled
    ? {
        enabled: true,
        collectionId: profile?.id ?? "",
        topK: parseInt(form.ragTopK) || 3,
        threshold: parseFloat(form.ragThreshold) || 0.7,
      }
    : null;

  return (
    <div>
      <PageHeader
        title={isEdit ? "編輯人格" : "新增人格"}
        description={isEdit ? `ID: ${profile.id}` : "建立一個新的 Role 設定"}
      />

      <form onSubmit={submit} className="space-y-5">
        <Tabs defaultValue="basic">
          <TabsList className="w-full">
            <TabsTrigger value="basic" className="flex-1">基本</TabsTrigger>
            <TabsTrigger value="tools" className="flex-1">工具</TabsTrigger>
            {isEdit && (
              <TabsTrigger value="knowledge" className="flex-1">知識庫</TabsTrigger>
            )}
          </TabsList>

          {/* ── 基本 ── */}
          <TabsContent value="basic" className="space-y-4 pt-4">
            <Field label="名稱" required htmlFor="name">
              <Input id="name" required placeholder="例：公車站長" value={form.name}
                onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="說明" htmlFor="description">
              <Input id="description" placeholder="簡短描述此人格的用途" value={form.description}
                onChange={(e) => set("description", e.target.value)} />
            </Field>
            <Field label="系統提示詞" required htmlFor="systemPrompt">
              <Textarea id="systemPrompt" required rows={12} className="font-mono text-sm resize-y"
                placeholder="你是..." value={form.systemPrompt}
                onChange={(e) => set("systemPrompt", e.target.value)} />
            </Field>
            <Separator />
            <label className="flex items-start gap-2.5 cursor-pointer">
              <Checkbox checked={form.isActive} onCheckedChange={(v) => set("isActive", v)} className="mt-0.5" />
              <div>
                <p className="text-sm font-medium">啟用此人格</p>
                <p className="text-xs text-muted-foreground">啟用後將替換目前使用中的人格</p>
                {!form.isActive && (
                  <p className="text-xs text-amber-500 mt-0.5">若所有人格皆停用，Worker 將無人格可用</p>
                )}
              </div>
            </label>
          </TabsContent>

          {/* ── 工具 ── */}
          <TabsContent value="tools" className="space-y-2 pt-4">
            {TOOL_GROUPS.map((group) => (
              <div key={group.label} className="rounded-lg border p-3">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <Checkbox
                    checked={group.tools.every((n) => form.tools.includes(n))}
                    onCheckedChange={(checked) => {
                      const others = form.tools.filter((t) => !group.tools.includes(t));
                      set("tools", checked ? [...others, ...group.tools] : others);
                    }}
                    className="mt-0.5"
                  />
                  <div>
                    <p className="text-sm font-medium leading-none">{group.label}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{group.description}</p>
                  </div>
                </label>
              </div>
            ))}
          </TabsContent>

          {/* ── 知識庫 ── */}
          {isEdit && (
            <TabsContent value="knowledge" className="space-y-4 pt-4">
              {/* RAG settings */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">RAG 設定</CardTitle>
                  <CardDescription>每輪對話自動從知識庫檢索相關內容</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <label className="flex items-center gap-2.5 cursor-pointer">
                    <Checkbox checked={form.ragEnabled}
                      onCheckedChange={(v) => set("ragEnabled", v)} />
                    <span className="text-sm font-medium">啟用 RAG 檢索</span>
                  </label>
                  {form.ragEnabled && (
                    <div className="grid grid-cols-2 gap-4">
                      <Field label="Top-K" htmlFor="ragTopK">
                        <Input id="ragTopK" type="number" min="1" max="10" step="1"
                          value={form.ragTopK} onChange={(e) => set("ragTopK", e.target.value)} />
                      </Field>
                      <Field label="相似度門檻" htmlFor="ragThreshold">
                        <Input id="ragThreshold" type="number" min="0" max="1" step="0.05"
                          value={form.ragThreshold} onChange={(e) => set("ragThreshold", e.target.value)} />
                      </Field>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Document management */}
              <KnowledgeCollection
                profileName={profile.name}
                collectionId={profile.id}
                ragConfig={ragConfig}
                initialChunks={knowledgeData?.initialChunks ?? []}
                initialChunksHasMore={knowledgeData?.initialChunksHasMore ?? false}
                initialJobs={knowledgeData?.initialJobs ?? []}
              />
            </TabsContent>
          )}
        </Tabs>

        {/* Save bar */}
        <div className="flex gap-3 pt-1">
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
