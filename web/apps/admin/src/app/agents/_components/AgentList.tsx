"use client";

import { startTransition, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AgentProfile } from "@taigi-flow/db";
import { BookOpen, Plus, Radio, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { confirmDialog } from "@/components/confirm-dialog";
import { PageHeader } from "@/components/page-header";
import { cn } from "@/lib/utils";

export default function AgentList({ initial }: { initial: AgentProfile[] }) {
  const router = useRouter();
  const [profiles, setProfiles] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setProfiles(initial);
  }, [initial]);

  async function errorMessage(res: Response, fallback: string) {
    const data = await res.json().catch(() => null);
    if (data && typeof data.error === "string") return data.error;
    return `${fallback} (${res.status})`;
  }

  async function activate(p: AgentProfile) {
    if (p.isActive) return;
    setBusy(p.id);
    try {
      const res = await fetch(`/api/agent-profiles/${p.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isActive: true }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, "啟用失敗"));
      setProfiles((prev) => prev.map((x) => ({ ...x, isActive: x.id === p.id })));
      startTransition(() => router.refresh());
      toast.success(`已啟用「${p.name}」`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "啟用失敗");
    } finally {
      setBusy(null);
    }
  }

  async function deleteProfile(e: React.MouseEvent, p: AgentProfile) {
    e.stopPropagation();
    const ok = await confirmDialog({
      title: "刪除人格",
      description: `確定要刪除「${p.name}」？此操作無法復原。`,
      confirmLabel: "刪除",
    });
    if (!ok) return;
    setBusy(p.id);
    try {
      const res = await fetch(`/api/agent-profiles/${p.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await errorMessage(res, "刪除失敗"));
      setProfiles((prev) => prev.filter((x) => x.id !== p.id));
      startTransition(() => router.refresh());
      toast.success(`已刪除「${p.name}」`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "刪除失敗");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Role"
        description="同一時間只能啟用一個，切換後下次連線自動套用"
        action={
          <Link href="/agents/new" className={cn(buttonVariants({ size: "sm" }), "gap-1.5")}>
            <Plus className="size-4" />
            新增人格
          </Link>
        }
      />

      {profiles.length === 0 && (
        <p className="text-muted-foreground text-sm py-8 text-center">
          尚無 Role，請新增一個。
        </p>
      )}

      <div className="space-y-2">
        {profiles.map((p) => (
          <div
            key={p.id}
            className={cn(
              "flex items-center gap-4 p-4 rounded-lg border transition-colors cursor-pointer",
              p.isActive
                ? "border-primary/40 bg-primary/5 hover:bg-primary/10"
                : "border-border bg-card hover:bg-accent/30",
            )}
            onClick={() => router.push(`/agents/${p.id}`)}
          >
            {/* Active toggle — click stops propagation to prevent nav */}
            <button
              className="shrink-0 p-0.5 rounded"
              title={p.isActive ? "目前啟用中" : "點擊啟用"}
              disabled={p.isActive || busy === p.id}
              onClick={(e) => { e.stopPropagation(); void activate(p); }}
            >
              <Radio
                className={cn(
                  "size-5",
                  p.isActive ? "text-primary" : "text-muted-foreground/40",
                )}
              />
            </button>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                {p.isActive && <Badge variant="secondary">使用中</Badge>}
              </div>
              {p.description && (
                <p className="text-sm text-muted-foreground mt-0.5 truncate">{p.description}</p>
              )}
            </div>

            {/* Direct action buttons */}
            <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
              <Button
                variant="ghost"
                size="icon-sm"
                title="RAG"
                onClick={() => router.push(`/knowledge/${p.id}`)}
              >
                <BookOpen className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                title="刪除"
                disabled={busy === p.id}
                className="text-muted-foreground hover:text-destructive"
                onClick={(e) => void deleteProfile(e, p)}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
